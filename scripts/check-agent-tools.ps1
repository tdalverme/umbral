[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\unit\agent\tools",
    "tests\unit\application\agent\tools",
    "tests\unit\infrastructure\agent\tools",
    "tests\unit\config\test_agent_settings.py",
    "tests\contract\test_agent_tools_contract.py",
    "tests\contract\test_agent_state_schema_v2.py",
    "tests\contract\test_agent_graph_topology_v2.py",
    "tests\contract\test_agent_reply_schema_v2.py",
    "tests\contract\test_agent_tool_events.py",
    "tests\contract\test_agent_tools_harness.py",
    "tests\architecture\test_agent_boundaries.py",
    "tests\integration\agent\tools",
    "tests\migrations\test_0010_agent_tools.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Agent tools surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Agent tools checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks agent tools (contract, executor, proposals, read tools, feedback, urban, abuse, migration 0010)"
