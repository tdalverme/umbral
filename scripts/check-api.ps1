[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonPath = $pythonCommand.Source
    }
}

if (-not (Test-Path -LiteralPath $pythonPath) -and -not (Get-Command $pythonPath -ErrorAction SilentlyContinue)) {
    throw "No hay Python disponible para inspeccionar la API."
}

$sourcePath = Join-Path $repoRoot "src"
$previousPythonPath = $env:PYTHONPATH
$pythonCode = @"
from umbral.api.main import app

paths = app.openapi().get('paths', {})
if '/health' not in paths:
    raise SystemExit('OpenAPI no expone /health')
"@

try {
    if (Test-Path -LiteralPath $sourcePath) {
        if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
            $env:PYTHONPATH = $sourcePath
        }
        else {
            $env:PYTHONPATH = $sourcePath + [System.IO.Path]::PathSeparator + $previousPythonPath
        }
    }

    & $pythonPath -c $pythonCode
    $pythonExitCode = $LASTEXITCODE
    if ($pythonExitCode -ne 0) {
        throw "La inspeccion de OpenAPI termino con codigo $pythonExitCode."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host "[PASS] Import de API y contrato OpenAPI basico"
