[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\unit\application\criteria",
    "tests\unit\infrastructure\criteria",
    "tests\contract\test_concept_registry.py",
    "tests\contract\test_extraction_rules.py",
    "tests\contract\test_extraction_versions.py",
    "tests\contract\test_compilation.py",
    "tests\contract\test_extraction_goldens.py",
    "tests\contract\test_events_registry.py",
    "tests\integration\criteria",
    "tests\migrations\test_0006_criteria_observations.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Criteria surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Criteria checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks criteria (concept registry, facts, compilation, extraction, recompute, events)"
