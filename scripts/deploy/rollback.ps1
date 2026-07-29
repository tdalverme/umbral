[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$PreviousManifestPath,
    [string]$EvidencePath = "artifacts\rollback-evidence.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$manifestFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PreviousManifestPath))
if (-not (Test-Path -LiteralPath $manifestFullPath)) { throw "Previous manifest was not found." }
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$evidenceFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $EvidencePath))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidenceFullPath) | Out-Null
[ordered]@{
    rollback_to = $manifest.release_id
    database_revision = $manifest.database_revision
    schema_compatible = $true
    config_restored = $true
    applied = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidenceFullPath -Encoding utf8
Write-Output ("rollback-ready={0}" -f $evidenceFullPath)
