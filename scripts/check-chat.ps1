[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\contract\test_agent_state_schema_v3.py",
    "tests\contract\test_agent_graph_topology_v3.py",
    "tests\contract\test_agent_reply_schema_v3.py",
    "tests\contract\test_agent_intent_schema_v3.py",
    "tests\contract\test_chat_streaming_contract.py",
    "tests\contract\test_chat_http_contract.py",
    "tests\unit\agent\intent",
    "tests\unit\agent\test_runtime_v3.py",
    "tests\unit\agent\test_grounding.py",
    "tests\unit\agent\test_abuse_suite_v3.py",
    "tests\unit\application\chat\test_message_idempotency.py",
    "tests\unit\application\agent\tools\test_proposal_transitions.py",
    "tests\unit\config\test_agent_settings.py",
    "tests\integration\chat\test_hitl_lifecycle.py",
    "tests\integration\chat\test_edit_chain.py",
    "tests\integration\chat\test_streaming_router.py",
    "tests\integration\api\test_chat_e2e.py",
    "tests\architecture\test_agent_boundaries.py",
    "tests\migrations\test_0011_chat_streaming.py"
)
foreach ($path in $testPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path))) {
        throw "Conversational UI surface detected but missing test path: $path"
    }
}
Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m pytest @testPaths -q
    if ($LASTEXITCODE -ne 0) { throw "Conversational UI checks failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
Write-Host "[PASS] Checks chat conversational UI (contracts v3, intent, clarification, HITL, grounded, streaming router, E2E, abuse v3, migration 0011)"
