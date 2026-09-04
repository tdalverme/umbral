[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$testPaths = @(
    "tests\contract\test_chat_streaming_contract.py",
    "tests\contract\test_chat_http_contract.py",
    "tests\unit\agent\intent",
    "tests\unit\application\chat\test_message_idempotency.py",
    "tests\unit\application\agent\tools\test_proposal_transitions.py",
    "tests\unit\config\test_agent_settings.py",
    "tests\integration\chat\test_hitl_lifecycle.py",
    "tests\integration\chat\test_semantic_preferences.py",
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
Write-Host "[PASS] Checks chat conversational UI (single-stack intent, HITL stepper, semantic preferences, E2E, migration 0011)"
