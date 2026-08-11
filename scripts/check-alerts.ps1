[CmdletBinding()]
param()

# Proactive alerts harness (H5): contracts, planner golden gate, unit,
# integration with Postgres, migration 0013, architecture and config.
$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\contract\test_notifications_policy.py",
    "tests\contract\test_notifications_planner_golden.py",
    "tests\contract\test_notification_events.py",
    "tests\unit\application\notifications",
    "tests\unit\config\test_notifications_settings.py",
    "tests\integration\notifications",
    "tests\architecture\test_notifications_boundaries.py",
    "tests\migrations\test_0013_notifications.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Notifications surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Notifications checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks proactive alerts (policy, planner golden gate, events, unit, integration, migration 0013, architecture, config)"
