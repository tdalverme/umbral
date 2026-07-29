[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ReleaseId,
    [Parameter(Mandatory = $true)] [string]$GitSha,
    [Parameter(Mandatory = $true)] [string]$DatabaseRevision,
    [Parameter(Mandatory = $true)] [string]$WebImage,
    [Parameter(Mandatory = $true)] [string]$WebDigest,
    [Parameter(Mandatory = $true)] [string]$RuntimeImage,
    [Parameter(Mandatory = $true)] [string]$RuntimeDigest,
    [int]$ConfigSchemaVersion = 1,
    [string]$ManifestPath = "artifacts\release-manifest.json"
)

$ErrorActionPreference = "Stop"
$shaPattern = "^[0-9a-f]{40}$"
$digestPattern = "^sha256:[0-9a-f]{64}$"
if ($GitSha -notmatch $shaPattern) { throw "GitSha must be a 40-character lowercase commit SHA." }
if ($WebDigest -notmatch $digestPattern -or $RuntimeDigest -notmatch $digestPattern) {
    throw "Artifact digests must be immutable sha256 references."
}
if ($ConfigSchemaVersion -lt 1) { throw "ConfigSchemaVersion must be positive." }

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$manifestFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
$manifestDirectory = Split-Path -Parent $manifestFullPath
New-Item -ItemType Directory -Force -Path $manifestDirectory | Out-Null
$manifest = [ordered]@{
    schema_version = 1
    release_id = $ReleaseId
    git_sha = $GitSha
    built_at = [DateTime]::UtcNow.ToString("o")
    contract_major = 1
    database_revision = $DatabaseRevision
    config_schema_version = $ConfigSchemaVersion
    artifacts = [ordered]@{
        web = [ordered]@{ image = $WebImage; digest = $WebDigest; platform = "linux/amd64" }
        runtime = [ordered]@{ image = $RuntimeImage; digest = $RuntimeDigest; platform = "linux/amd64" }
    }
}
$json = $manifest | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($manifestFullPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$checksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
Write-Output ("manifest={0}" -f $manifestFullPath)
Write-Output ("manifest_sha256={0}" -f $checksum)
