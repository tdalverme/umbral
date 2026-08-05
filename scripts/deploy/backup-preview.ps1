[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$EvidencePath
)

$ErrorActionPreference = "Stop"

function Require-Environment([string]$Name) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) {
        throw ("Required release setting is missing: {0}." -f $Name)
    }
}

function Invoke-Aws([string[]]$Arguments) {
    $output = & aws @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Object storage backup operation failed." }
    return $output
}

foreach ($name in @("DATABASE_URL", "OBJECT_STORE_BUCKET", "OBJECT_STORE_ENDPOINT_URL", "OBJECT_STORE_ACCESS_KEY", "OBJECT_STORE_SECRET_KEY")) {
    Require-Environment $name
}
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Release manifest was not found." }
if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) { throw "pg_dump is required for a preview backup." }
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) { throw "AWS CLI is required for the object storage backup." }

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$manifestFullPath = [System.IO.Path]::GetFullPath($ManifestPath)
$evidenceFullPath = [System.IO.Path]::GetFullPath($EvidencePath)
$releaseManifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$backupId = "preview-{0}-{1}" -f ([DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")), ([guid]::NewGuid().ToString("N"))
$createdAt = [DateTime]::UtcNow.ToString("o")
$temporaryDump = Join-Path ([System.IO.Path]::GetTempPath()) ("{0}.dump" -f $backupId)
$temporaryManifest = Join-Path ([System.IO.Path]::GetTempPath()) ("{0}.json" -f $backupId)
$dumpKey = "backups/preview/{0}/database.dump" -f $backupId
$manifestKey = "backups/preview/{0}/manifest.json" -f $backupId

$previousAccessKey = $env:AWS_ACCESS_KEY_ID
$previousSecretKey = $env:AWS_SECRET_ACCESS_KEY
$previousMetadata = $env:AWS_EC2_METADATA_DISABLED
try {
    $env:AWS_ACCESS_KEY_ID = $env:OBJECT_STORE_ACCESS_KEY
    $env:AWS_SECRET_ACCESS_KEY = $env:OBJECT_STORE_SECRET_KEY
    $env:AWS_EC2_METADATA_DISABLED = "true"

    $databaseUri = [Uri]::new($env:DATABASE_URL)
    if ([string]::IsNullOrWhiteSpace($databaseUri.Host)) {
        throw "DATABASE_URL does not contain a host; pg_dump would fall back to a local socket."
    }
    Write-Host "Backup database host: $($databaseUri.Host):$($databaseUri.Port)"

    $pgDumpError = (& pg_dump --format=custom --file $temporaryDump $env:DATABASE_URL 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $temporaryDump)) {
        throw ("Database backup failed: {0}" -f $pgDumpError)
    }

    $dumpHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $temporaryDump).Hash.ToLowerInvariant()
    $dumpSize = (Get-Item -LiteralPath $temporaryDump).Length
    $backupManifest = [ordered]@{
        backup_id = $backupId
        created_at = $createdAt
        database_dump_key = $dumpKey
        database_dump_sha256 = $dumpHash
        database_dump_size_bytes = $dumpSize
        manifest_revision = [string]$releaseManifest.database_revision
    }
    [System.IO.File]::WriteAllText($temporaryManifest, ($backupManifest | ConvertTo-Json -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

    Invoke-Aws @("--endpoint-url", $env:OBJECT_STORE_ENDPOINT_URL, "s3api", "put-object", "--bucket", $env:OBJECT_STORE_BUCKET, "--key", $dumpKey, "--body", $temporaryDump, "--metadata", ("sha256={0},backup-id={1}" -f $dumpHash, $backupId)) | Out-Null
    Invoke-Aws @("--endpoint-url", $env:OBJECT_STORE_ENDPOINT_URL, "s3api", "put-object", "--bucket", $env:OBJECT_STORE_BUCKET, "--key", $manifestKey, "--body", $temporaryManifest) | Out-Null
    $head = (Invoke-Aws @("--endpoint-url", $env:OBJECT_STORE_ENDPOINT_URL, "s3api", "head-object", "--bucket", $env:OBJECT_STORE_BUCKET, "--key", $dumpKey) | Out-String | ConvertFrom-Json)
    if ([int64]$head.ContentLength -ne $dumpSize -or [string]$head.Metadata.sha256 -ne $dumpHash) { throw "Object storage backup verification failed." }

    $evidence = [ordered]@{
        backup_id = $backupId
        created_at = $createdAt
        database_dump_key = $dumpKey
        database_dump_sha256 = $dumpHash
        database_dump_size_bytes = $dumpSize
        manifest_key = $manifestKey
        manifest_revision = [string]$releaseManifest.database_revision
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidenceFullPath) | Out-Null
    [System.IO.File]::WriteAllText($evidenceFullPath, ($evidence | ConvertTo-Json -Compress) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    $evidence | ConvertTo-Json -Compress
}
finally {
    Remove-Item -LiteralPath $temporaryDump -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporaryManifest -Force -ErrorAction SilentlyContinue
    $env:AWS_ACCESS_KEY_ID = $previousAccessKey
    $env:AWS_SECRET_ACCESS_KEY = $previousSecretKey
    $env:AWS_EC2_METADATA_DISABLED = $previousMetadata
}
