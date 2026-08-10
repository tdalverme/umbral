[CmdletBinding()]
param(
    [int]$CaseLimit = 0,
    [double]$CostCapUsd = 0
)

# Opt-in real-provider eval flow (clarification Q4, R-12). NOT part of
# check.ps1: it calls the real model provider and must respect an eval budget.
$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

Push-Location $repoRoot
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    $args = @("-m", "umbral.infrastructure.agent_evals.real_flow")
    if ($CaseLimit -gt 0) { $args += "--case-limit"; $args += "$CaseLimit" }
    if ($CostCapUsd -gt 0) { $args += "--cost-cap-usd"; $args += "$CostCapUsd" }
    & $pythonPath @args
    if ($LASTEXITCODE -ne 0) { throw "Real-provider eval flow failed with code $LASTEXITCODE." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
