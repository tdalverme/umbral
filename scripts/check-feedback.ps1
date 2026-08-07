[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\unit\application\feedback",
    "tests\unit\application\radar\test_learning_seams.py",
    "tests\contract\test_quick_reasons.py",
    "tests\contract\test_learning_policy.py",
    "tests\contract\test_feedback_endpoints.py",
    "tests\contract\test_learning_endpoints.py",
    "tests\contract\test_events_registry.py",
    "tests\architecture\test_feedback_boundaries.py",
    "tests\integration\feedback",
    "tests\migrations\test_0008_feedback_learning.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Feedback surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Feedback checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks feedback (events, reasons, learning policy, proposals, endpoints, integration, migration 0008)"
