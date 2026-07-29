[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$BaselinePath,
    [Parameter(Mandatory)]
    [string]$CandidatePath
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing: $python"
}

$comparisonProgram = @'
import json
import sys
from pathlib import Path


def read_document(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def properties(document: dict, schema_name: str) -> dict:
    return document['components']['schemas'][schema_name].get('properties', {})


baseline = read_document(sys.argv[1])
candidate = read_document(sys.argv[2])
breaks = []

for schema_name in baseline.get('components', {}).get('schemas', {}):
    candidate_schemas = candidate.get('components', {}).get('schemas', {})
    if schema_name not in candidate_schemas:
        breaks.append(f'missing schema: {schema_name}')
        continue
    for property_name, baseline_property in properties(baseline, schema_name).items():
        candidate_properties = properties(candidate, schema_name)
        if property_name not in candidate_properties:
            breaks.append(f'missing property: {schema_name}.{property_name}')
        elif candidate_properties[property_name] != baseline_property:
            breaks.append(f'changed property: {schema_name}.{property_name}')

if breaks:
    print('breaking OpenAPI change(s): ' + '; '.join(breaks), file=sys.stderr)
    raise SystemExit(1)
'@

& $python -c $comparisonProgram $BaselinePath $CandidatePath
exit $LASTEXITCODE
