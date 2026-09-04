[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\unit\agent",
    "tests\unit\application\chat",
    "tests\unit\application\agent",
    "tests\unit\application\agent\tools",
    "tests\unit\infrastructure\agent",
    "tests\unit\config\test_agent_settings.py",
    "tests\contract\test_agent_contracts.py",
    "tests\contract\test_agent_chat_events.py",
    "tests\architecture\test_agent_boundaries.py",
    "tests\architecture\test_single_agent_generation.py",
    "tests\integration\chat",
    "tests\migrations\test_0009_langgraph_runtime.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Agent surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Agent checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks single semantic agent (contracts, intent, graph, runtime, chat, migration 0009)"
