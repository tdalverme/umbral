[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\unit\application\matching",
    "tests\unit\application\criteria\test_compile_forbidden_concepts.py",
    "tests\contract\test_matching_golden.py",
    "tests\contract\test_matching_regression.py",
    "tests\contract\test_matching_fidelity.py",
    "tests\contract\test_matching_fairness.py",
    "tests\contract\test_matching_harness.py",
    "tests\architecture\test_matching_boundaries.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Matching surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Matching quality checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks matching quality (golden dataset, regressions, fidelity, fairness, boundaries, harness)"
