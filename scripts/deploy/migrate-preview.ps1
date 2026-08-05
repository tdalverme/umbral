[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$BackupEvidencePath,
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) { throw "Required release setting is missing: DATABASE_URL." }
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Release manifest was not found." }
if (-not (Test-Path -LiteralPath $BackupEvidencePath)) { throw "Verified backup evidence was not found." }

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $localPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $PythonExecutable = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}
$env:PYTHONPATH = Join-Path $repoRoot "src"
$manifest = Get-Content -Raw -LiteralPath ([System.IO.Path]::GetFullPath($ManifestPath)) | ConvertFrom-Json
$backupEvidence = Get-Content -Raw -LiteralPath ([System.IO.Path]::GetFullPath($BackupEvidencePath)) | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace([string]$backupEvidence.backup_id) -or [string]::IsNullOrWhiteSpace([string]$backupEvidence.database_dump_sha256) -or $backupEvidence.manifest_revision -ne $manifest.database_revision) {
    throw "Backup evidence does not match the release manifest."
}

# Alembic receives the single Railway URL; role-split migration URLs no longer exist.
$alembicErrorFile = Join-Path ([System.IO.Path]::GetTempPath()) ("alembic-{0}.txt" -f [guid]::NewGuid().ToString("N"))
& $PythonExecutable -m alembic upgrade head 2> $alembicErrorFile
$alembicError = Get-Content -Raw -LiteralPath $alembicErrorFile
Remove-Item -LiteralPath $alembicErrorFile -Force -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) {
    Write-Host "Alembic upgrade failed; full error:"
    Write-Host $alembicError
    throw ("Alembic migration failed: {0}" -f $alembicError)
}
$dbStateErrorFile = Join-Path ([System.IO.Path]::GetTempPath()) ("dbstate-{0}.txt" -f [guid]::NewGuid().ToString("N"))
$databaseState = & $PythonExecutable -c "import json, os, psycopg; c=psycopg.connect(os.environ['DATABASE_URL']); q=c.cursor(); q.execute('select version_num from alembic_version'); r=q.fetchone()[0]; q.execute(\"select extname from pg_extension where extname in ('postgis','vector')\"); print(json.dumps({'revision': r, 'extensions': sorted(x[0] for x in q.fetchall())}))" 2> $dbStateErrorFile
$dbStateError = Get-Content -Raw -LiteralPath $dbStateErrorFile
Remove-Item -LiteralPath $dbStateErrorFile -Force -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) {
    Write-Host "Database conformance query failed; full error:"
    Write-Host $dbStateError
    throw ("Database conformance query failed: {0}" -f $dbStateError)
}
$state = ($databaseState | Out-String | ConvertFrom-Json)
if ($state.revision -ne $manifest.database_revision -or @($state.extensions).Count -ne 2 -or @($state.extensions | Where-Object { $_ -notin @('postgis', 'vector') }).Count -ne 0) {
    throw "Migration revision or required extensions are invalid."
}
[ordered]@{ revision = $state.revision; extensions = @($state.extensions) } | ConvertTo-Json -Compress
