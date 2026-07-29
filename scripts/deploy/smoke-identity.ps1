[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $repoRoot "src"
& $pythonPath -c "from umbral.ops.smoke import run_identity_smoke; print(run_identity_smoke())"
if ($LASTEXITCODE -ne 0) { throw "Identity smoke failed." }
