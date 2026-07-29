[CmdletBinding()]
param(
    [string]$OutputPath = "contracts/openapi/v1/openapi.json"
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing: $python"
}

$resolvedOutputPath = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $repositoryRoot $OutputPath
}
$outputDirectory = Split-Path -Parent $resolvedOutputPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

$env:PYTHONPATH = Join-Path $repositoryRoot "src"
$exportProgram = @'
import json
import sys
from pathlib import Path

from umbral.api.main import app

output_path = Path(sys.argv[1])
document = app.openapi()
output_path.write_text(
    json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
    encoding='utf-8',
)
'@

& $python -c $exportProgram $resolvedOutputPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
