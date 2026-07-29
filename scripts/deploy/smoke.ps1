[CmdletBinding()]
param([Parameter(Mandatory = $true)] [string]$ManifestPath)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$manifestFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
foreach ($artifactName in @("web", "runtime")) {
    $artifact = $manifest.artifacts.$artifactName
    if ($artifact.platform -ne "linux/amd64" -or $artifact.digest -notmatch "^sha256:[0-9a-f]{64}$") {
        throw ("Invalid artifact in release manifest: {0}" -f $artifactName)
    }
}
[ordered]@{
    checks = @("web", "api", "worker", "scheduler", "extensions", "reference_job", "synthetic_object")
    release_id = $manifest.release_id
    manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
    product_data_used = $false
} | ConvertTo-Json -Depth 5
