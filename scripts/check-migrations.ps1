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

    $ErrorActionPreference = "Continue"
    $upgradeSql = @(& $pythonPath -m alembic upgrade head --sql 2>&1)
    $upgradeExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($upgradeExitCode -ne 0) {
        throw "Alembic offline upgrade failed with exit code $upgradeExitCode."
    }
    $upgradeSqlText = $upgradeSql -join "`n"
    foreach ($requiredSql in @("CREATE TYPE actor_kind", "CREATE TABLE job_executions", "CREATE TABLE runtime_surface_status")) {
        if ($upgradeSqlText -notmatch [regex]::Escape($requiredSql)) {
            throw "Offline upgrade SQL is missing required operation: $requiredSql"
        }
    }
    Write-Host "[PASS] Alembic offline upgrade snapshot"

    $ErrorActionPreference = "Continue"
    $downgradeSql = @(& $pythonPath -m alembic downgrade 0001_foundation_runtime:base --sql 2>&1)
    $downgradeExitCode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($downgradeExitCode -ne 0) {
        throw "Alembic offline downgrade failed with exit code $downgradeExitCode."
    }
    $downgradeSqlText = $downgradeSql -join "`n"
    foreach ($requiredSql in @("DROP TABLE runtime_surface_status", "DROP TYPE IF EXISTS actor_kind")) {
        if ($downgradeSqlText -notmatch [regex]::Escape($requiredSql)) {
            throw "Offline downgrade SQL is missing required operation: $requiredSql"
        }
    }
    Write-Host "[PASS] Alembic offline downgrade snapshot"

    & $pythonPath -c "from umbral.infrastructure.db.migrations import expected_schema; expected={'job_executions','job_attempts','job_outbox_messages','job_schedules','stored_objects','stored_object_versions','runtime_surface_status','identity_invitations','product_users','external_identity_links','role_assignments','magic_link_requests','magic_link_attempts','product_sessions','access_audit_events','import_runs','raw_listing_snapshots','quarantine_records','canonical_properties','silver_listings','dedupe_links','listing_changes','search_profiles','search_profile_versions','recommendation_runs','recommendation_items','product_events','concepts','concept_versions','preference_facts','profile_criteria_compilations','extraction_versions','listing_observations','recomputation_runs','listing_embeddings','urban_signals','scoring_policies','scoring_policy_versions','criterion_evaluations','comparison_shortlists','feedback_events','feedback_event_reasons','learning_policies','learning_policy_versions','learning_proposals','chat_sessions','chat_messages','agent_graph_runs','agent_node_runs','agent_model_calls'}; actual=set(expected_schema().tables); assert actual == expected, (actual ^ expected)"
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
