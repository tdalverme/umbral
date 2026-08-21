[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\contract\test_feedback_concept_interpret.py",
    "tests\contract\test_extraction_rules.py",
    "tests\contract\test_extraction_goldens.py",
    "tests\unit\application\feedback\test_concept_signals.py",
    "tests\unit\application\criteria\test_rules_economic.py",
    "tests\integration\feedback\test_concept_feedback_e2e.py",
    "tests\integration\flows\test_spec_validation_flows.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Spec 019 surface is missing its test path: $path"
    }
}

Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) {
        throw "Spec 019 checks failed with code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks spec 019 (structured feedback, economic rules, golden path)"
