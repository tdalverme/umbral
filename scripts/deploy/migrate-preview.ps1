[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$BackupEvidencePath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:DATABASE_MIGRATION_URL)) { throw "Required release setting is missing: DATABASE_MIGRATION_URL." }
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Release manifest was not found." }
if (-not (Test-Path -LiteralPath $BackupEvidencePath)) { throw "Verified backup evidence was not found." }

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $repoRoot "src"
$manifest = Get-Content -Raw -LiteralPath ([System.IO.Path]::GetFullPath($ManifestPath)) | ConvertFrom-Json
$backupEvidence = Get-Content -Raw -LiteralPath ([System.IO.Path]::GetFullPath($BackupEvidencePath)) | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace([string]$backupEvidence.backup_id) -or [string]::IsNullOrWhiteSpace([string]$backupEvidence.database_dump_sha256) -or $backupEvidence.manifest_revision -ne $manifest.database_revision) {
    throw "Backup evidence does not match the release manifest."
}

$previousRuntimeDatabase = $env:DATABASE_URL
try {
    $env:DATABASE_URL = $env:DATABASE_MIGRATION_URL
    # Alembic receives the direct URL only in this migration job.
    & $pythonPath -m alembic upgrade head 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
    $databaseState = & $pythonPath -c "import json, os, psycopg; c=psycopg.connect(os.environ['DATABASE_URL']); q=c.cursor(); q.execute('select version_num from alembic_version'); r=q.fetchone()[0]; q.execute(\"select extname from pg_extension where extname in ('postgis','vector')\"); print(json.dumps({'revision': r, 'extensions': sorted(x[0] for x in q.fetchall())}))" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Database conformance query failed." }
    $state = ($databaseState | Out-String | ConvertFrom-Json)
    if ($state.revision -ne $manifest.database_revision -or @($state.extensions).Count -ne 2 -or @($state.extensions | Where-Object { $_ -notin @('postgis', 'vector') }).Count -ne 0) {
        throw "Migration revision or required extensions are invalid."
    }
    [ordered]@{ revision = $state.revision; extensions = @($state.extensions) } | ConvertTo-Json -Compress
}
finally {
    $env:DATABASE_URL = $previousRuntimeDatabase
}
