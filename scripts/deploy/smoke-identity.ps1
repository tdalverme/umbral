[CmdletBinding()]
param(
    [ValidateSet("local", "preview")] [string]$Mode = "local"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
if ($Mode -eq "preview") {
    throw "Preview identity smoke must run through smoke.ps1 with a release manifest and public BaseUrl."
}
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $repoRoot "src"
& $pythonPath -m umbral.ops.smoke local
if ($LASTEXITCODE -ne 0) { throw "Identity smoke failed." }
