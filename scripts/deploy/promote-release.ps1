[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$ManifestSha256,
    [Parameter(Mandatory = $true)] [ValidateSet("preview", "production")] [string]$Environment,
    [switch]$AccessPassed,
    [switch]$BackupPassed,
    [switch]$MigrationPassed,
    [switch]$SmokePassed,
    [string]$EvidencePath = "artifacts\promotion-evidence.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$manifestFullPath = if ([System.IO.Path]::IsPathRooted($ManifestPath)) {
    [System.IO.Path]::GetFullPath($ManifestPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
}
if (-not (Test-Path -LiteralPath $manifestFullPath)) { throw "Release manifest was not found." }
$actualChecksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
if ($ManifestSha256 -notmatch "^[0-9a-f]{64}$" -or $actualChecksum -ne $ManifestSha256) {
    throw "Release manifest checksum does not match."
}
$gates = [ordered]@{
    access = [bool]$AccessPassed
    backup = [bool]$BackupPassed
    migration = [bool]$MigrationPassed
    smoke = [bool]$SmokePassed
}
foreach ($gate in $gates.GetEnumerator()) {
    if (-not $gate.Value) { throw ("Promotion gate failed: {0}" -f $gate.Key) }
}
$null = & (Join-Path $PSScriptRoot "validate-railway-config.ps1") -ManifestPath $manifestFullPath
$switch = & (Join-Path $PSScriptRoot "set-railway-images.ps1") -ManifestPath $manifestFullPath -ManifestSha256 $ManifestSha256 -Environment $Environment | ConvertFrom-Json
$wait = & (Join-Path $PSScriptRoot "wait-railway-services.ps1") -Environment $Environment -DeploymentIdsJson ($switch.deployment_ids | ConvertTo-Json -Compress) | ConvertFrom-Json
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$evidenceFullPath = if ([System.IO.Path]::IsPathRooted($EvidencePath)) {
    [System.IO.Path]::GetFullPath($EvidencePath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $EvidencePath))
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidenceFullPath) | Out-Null
$evidence = [ordered]@{
    environment = $Environment
    release_id = $manifest.release_id
    manifest_sha256 = $ManifestSha256
    database_revision = $manifest.database_revision
    gates = $gates
    order = @("access", "backup", "migration", "smoke")
    deployment_ids = $wait.deployment_ids
    deployed = $true
} | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($evidenceFullPath, $evidence + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Output ("promotion-ready={0}" -f $evidenceFullPath)
