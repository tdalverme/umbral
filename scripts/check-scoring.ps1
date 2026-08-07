[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\unit\application\scoring",
    "tests\contract\test_scoring_policy.py",
    "tests\contract\test_evaluators.py",
    "tests\contract\test_explanations.py",
    "tests\contract\test_comparison.py",
    "tests\contract\test_explanation_endpoints.py",
    "tests\contract\test_events_registry.py",
    "tests\architecture\test_scoring_boundaries.py",
    "tests\integration\scoring",
    "tests\migrations\test_0007_scoring_explanations.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Scoring surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Scoring checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks scoring (policy, evaluators, engine, explanations, comparison, runs v1, events)"
