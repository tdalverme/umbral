[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [ValidateSet("preview", "production")] [string]$Environment,
    [switch]$AccessPassed,
    [switch]$BackupPassed,
    [switch]$MigrationPassed,
    [switch]$SmokePassed,
    [string]$EvidencePath = "artifacts\promotion-evidence.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$manifestFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
if (-not (Test-Path -LiteralPath $manifestFullPath)) { throw "Release manifest was not found." }
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$gates = [ordered]@{
    access = [bool]$AccessPassed
    backup = [bool]$BackupPassed
    migration = [bool]$MigrationPassed
    smoke = [bool]$SmokePassed
}
foreach ($gate in $gates.GetEnumerator()) {
    if (-not $gate.Value) { throw ("Promotion gate failed: {0}" -f $gate.Key) }
}
$evidenceFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $EvidencePath))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidenceFullPath) | Out-Null
[ordered]@{
    environment = $Environment
    release_id = $manifest.release_id
    database_revision = $manifest.database_revision
    gates = $gates
    order = @("access", "backup", "migration", "smoke")
    deployed = $false
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidenceFullPath -Encoding utf8
Write-Output ("promotion-ready={0}" -f $evidenceFullPath)
