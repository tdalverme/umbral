[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\integration\recovery",
    "tests\unit\ops\test_release_ops.py"
)
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Recovery checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks recovery (backup, restore and recovery gates)"
