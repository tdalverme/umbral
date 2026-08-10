[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\contract\test_agent_evals_golden.py",
    "tests\contract\test_agent_evals_releases.py",
    "tests\contract\test_agent_evals_price.py",
    "tests\contract\test_agent_evals_regression.py",
    "tests\contract\test_model_provider_adr.py",
    "tests\unit\application\agent_evals",
    "tests\unit\application\agent\test_budgets.py",
    "tests\unit\application\agent_ops",
    "tests\unit\config\test_agent_settings.py",
    "tests\integration\agent_evals\test_suite_lifecycle.py",
    "tests\integration\agent_evals\test_run_release_stamp.py",
    "tests\integration\agent_evals\test_agent_budgets.py",
    "tests\integration\agent_ops\test_overview.py",
    "tests\architecture\test_agent_evals_boundaries.py",
    "tests\migrations\test_0012_agent_evals.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Agent evals surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Agent evals checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks agent evals (dataset golden, releases, price, regression gate, budgets, dashboard, ADR, migration 0012)"
