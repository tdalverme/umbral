[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:DATABASE_URL
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot "alembic.ini"))) {
    throw "Migration surface detected but alembic.ini is missing."
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Migration surface detected but the repository Python interpreter is missing: $pythonPath"
}

Push-Location $repoRoot
$originalPythonPath = $env:PYTHONPATH
$originalDatabaseUrl = $env:DATABASE_URL
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $DatabaseUrl
    }

    & $pythonPath -m alembic heads
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic heads failed with exit code $LASTEXITCODE."
    }

    & $pythonPath -c "from umbral.infrastructure.db.migrations import expected_schema; expected={'job_executions','job_attempts','job_outbox_messages','job_schedules','stored_objects','stored_object_versions','runtime_surface_status'}; actual=set(expected_schema().tables); assert actual == expected, (actual ^ expected)"
    if ($LASTEXITCODE -ne 0) {
        throw "Foundation metadata inventory does not match the bootstrap contract."
    }

    if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
        Write-Host "[SKIP] Alembic live drift: DATABASE_URL is not configured."
    }
    else {
        & $pythonPath -m alembic check
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic metadata drift check failed with exit code $LASTEXITCODE."
        }
        Write-Host "[PASS] Alembic live drift"
    }
}
finally {
    $env:PYTHONPATH = $originalPythonPath
    if ($null -eq $originalDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DATABASE_URL = $originalDatabaseUrl
    }
    Pop-Location
}

Write-Host "[PASS] Migration graph and metadata"
exit 0
