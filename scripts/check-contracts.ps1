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


def mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def operations(path_item: object) -> dict:
    return {
        method: operation
        for method, operation in mapping(path_item).items()
        if method.lower() in {'get', 'put', 'post', 'delete', 'patch', 'head'}
        and isinstance(operation, dict)
    }


def effective_security(document: dict, operation: dict) -> object:
    return operation['security'] if 'security' in operation else document.get('security', [])


baseline = read_document(sys.argv[1])
candidate = read_document(sys.argv[2])
breaks = []

baseline_schemas = mapping(mapping(baseline.get('components')).get('schemas'))
candidate_schemas = mapping(mapping(candidate.get('components')).get('schemas'))
for schema_name in baseline_schemas:
    if schema_name not in candidate_schemas:
        breaks.append(f'missing schema: {schema_name}')
        continue
    for property_name, baseline_property in properties(baseline, schema_name).items():
        candidate_properties = properties(candidate, schema_name)
        if property_name not in candidate_properties:
            breaks.append(f'missing property: {schema_name}.{property_name}')
        elif candidate_properties[property_name] != baseline_property:
            breaks.append(f'changed property: {schema_name}.{property_name}')
    baseline_required = set(mapping(baseline_schemas[schema_name]).get('required', []))
    candidate_required = set(mapping(candidate_schemas[schema_name]).get('required', []))
    if not baseline_required.issubset(candidate_required):
        breaks.append(f'removed required property: {schema_name}')
    if not candidate_required.issubset(baseline_required):
        breaks.append(f'new required property: {schema_name}')

baseline_paths = mapping(baseline.get('paths'))
candidate_paths = mapping(candidate.get('paths'))
for path, baseline_path_item in baseline_paths.items():
    if path not in candidate_paths:
        breaks.append(f'missing path: {path}')
        continue
    candidate_operations = operations(candidate_paths[path])
    for method, baseline_operation in operations(baseline_path_item).items():
        if method not in candidate_operations:
            breaks.append(f'missing operation: {method.upper()} {path}')
            continue
        candidate_operation = candidate_operations[method]
        if baseline_operation.get('operationId') != candidate_operation.get('operationId'):
            breaks.append(f'changed operationId: {method.upper()} {path}')
        baseline_responses = mapping(baseline_operation.get('responses'))
        candidate_responses = mapping(candidate_operation.get('responses'))
        for status, baseline_response in baseline_responses.items():
            if status not in candidate_responses:
                breaks.append(f'missing response: {method.upper()} {path} {status}')
                continue
            candidate_response = candidate_responses[status]
            if mapping(baseline_response).get('content') != mapping(candidate_response).get('content'):
                breaks.append(f'changed response content: {method.upper()} {path} {status}')
            if mapping(baseline_response).get('headers') != mapping(candidate_response).get('headers'):
                breaks.append(f'changed response headers: {method.upper()} {path} {status}')
        if effective_security(baseline, baseline_operation) != effective_security(candidate, candidate_operation):
            breaks.append(f'changed security: {method.upper()} {path}')

baseline_schemes = mapping(mapping(baseline.get('components')).get('securitySchemes'))
candidate_schemes = mapping(mapping(candidate.get('components')).get('securitySchemes'))
for scheme_name, baseline_scheme in baseline_schemes.items():
    if candidate_schemes.get(scheme_name) != baseline_scheme:
        breaks.append(f'changed security scheme: {scheme_name}')

if breaks:
    print('breaking OpenAPI change(s): ' + '; '.join(breaks), file=sys.stderr)
    raise SystemExit(1)
'@

& $python -c $comparisonProgram $BaselinePath $CandidatePath
exit $LASTEXITCODE
