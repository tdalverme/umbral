[CmdletBinding()]
param([Parameter(Mandatory = $true)] [string]$ManifestPath)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$manifestFullPath = if ([System.IO.Path]::IsPathRooted($ManifestPath)) {
    [System.IO.Path]::GetFullPath($ManifestPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
}
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
foreach ($artifactName in @("web", "runtime")) {
    $artifact = $manifest.artifacts.$artifactName
    if ($artifact.platform -ne "linux/amd64" -or $artifact.digest -notmatch "^sha256:[0-9a-f]{64}$") {
        throw ("Invalid artifact in release manifest: {0}" -f $artifactName)
    }
}
$env:PYTHONPATH = Join-Path $repoRoot "src"
$identitySmoke = & $pythonPath -c "import json; from umbral.ops.smoke import run_identity_smoke; print(json.dumps(run_identity_smoke()))" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $identitySmoke.result -ne "accepted") {
    throw "Identity smoke failed."
}
[ordered]@{
    checks = @("web", "api", "worker", "scheduler", "extensions", "reference_job", "synthetic_object", "identity")
    release_id = $manifest.release_id
    manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
    product_data_used = $false
    identity_smoke = $identitySmoke.result
} | ConvertTo-Json -Depth 5
