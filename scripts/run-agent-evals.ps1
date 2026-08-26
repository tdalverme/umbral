[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Baseline,
    [Parameter(Mandatory = $true)][string]$Candidate,
    [double]$CostCapUsd = 5
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonPath -m umbral.infrastructure.agent_evals.v3_flow `
        --baseline $Baseline `
        --candidate $Candidate `
        --cost-cap-usd $CostCapUsd
    $code = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
exit $code