[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$PreviousManifestPath,
    [ValidateSet("preview", "production")] [string]$Environment = "preview",
    [string]$EvidencePath = "artifacts\rollback-evidence.json",
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $localPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $PythonExecutable = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}
$manifestFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PreviousManifestPath))
if (-not (Test-Path -LiteralPath $manifestFullPath)) { throw "Previous manifest was not found." }
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$checksumPath = "$manifestFullPath.sha256"
$checksum = if (Test-Path -LiteralPath $checksumPath) { (Get-Content -Raw -LiteralPath $checksumPath).Trim() } else { "" }
$evidenceFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $EvidencePath))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidenceFullPath) | Out-Null

$started = [DateTime]::UtcNow
$deploymentIds = [ordered]@{}
$smokePassed = $false
$schemaCompatible = $false
$errorDetail = $null

function Write-RollbackEvidence {
    param(
        [string]$SchemaCompatible,
        [string]$Applied,
        [string]$SmokeResult,
        [string]$Error
    )
    [ordered]@{
        rollback_to = $manifest.release_id
        manifest_sha256 = $checksum
        database_revision = $manifest.database_revision
        schema_compatible = ($SchemaCompatible -eq "true")
        config_restored = $true
        applied = ($Applied -eq "true")
        smoke_result = $SmokeResult
        elapsed_seconds = [int]([DateTime]::UtcNow - $started).TotalSeconds
        error = $Error
        deployment_ids = $deploymentIds
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidenceFullPath -Encoding utf8
}

try {
    # Reject a schema-incompatible previous revision before switching images.
    if ([string]::IsNullOrWhiteSpace([string]$env:DATABASE_URL)) {
        throw "DATABASE_URL is required for rollback schema verification."
    }
    $revisionProbe = @'
import os, psycopg
conn = psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)
try:
    cur = conn.cursor()
    cur.execute("SELECT version_num FROM alembic_version")
    row = cur.fetchone()
    print(row[0] if row else "")
finally:
    conn.close()
'@
    $actualRevision = (& $PythonExecutable -c $revisionProbe).Trim()
    if ([string]::IsNullOrWhiteSpace($actualRevision)) {
        throw "Could not resolve the deployed Alembic revision."
    }
    if ($actualRevision -ne [string]$manifest.database_revision) {
        throw ("Schema incompatible: deployed {0} vs manifest {1}." -f $actualRevision, $manifest.database_revision)
    }
    $schemaCompatible = $true

    # Switch every service back to the previous immutable digests.
    $switch = ./scripts/deploy/set-railway-images.ps1 -ManifestPath $manifestFullPath -ManifestSha256 $checksum -Environment $Environment | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Rollback image switch failed." }
    $deploymentIds = [ordered]@{}
    foreach ($service in @("web", "api", "worker", "scheduler")) {
        $deploymentIds[$service] = [string]$switch.deployment_ids.$service
    }

    $null = ./scripts/deploy/wait-railway-services.ps1 -Environment $Environment -DeploymentIdsJson ($deploymentIds | ConvertTo-Json -Compress)

    # Verify the restored manifest with the full preview smoke.
    $smokeOut = & $PythonExecutable -m umbral.ops.smoke preview --base-url $env:UMBRAL_PREVIEW_BASE_URL --manifest-path $manifestFullPath 2>&1
    $smokeExit = $LASTEXITCODE
    $smokePassed = ($smokeExit -eq 0)
    Write-RollbackEvidence -SchemaCompatible "true" -Applied ($(if ($smokePassed) { "true" } else { "false" })) -SmokeResult ($(if ($smokePassed) { "passed" } else { "failed" })) -Error $null
    if (-not $smokePassed) {
        throw ("Rollback smoke failed (exit {0}): {1}" -f $smokeExit, ($smokeOut -join "`n"))
    }
    Write-Output ("rollback-applied={0}" -f $evidenceFullPath)
    exit 0
} catch {
    $errorDetail = $_.Exception.Message
    Write-RollbackEvidence -SchemaCompatible ($(if ($schemaCompatible) { "true" } else { "false" })) -Applied "false" -SmokeResult ($(if ($smokePassed) { "passed" } else { "failed" })) -Error $errorDetail
    Write-Error $errorDetail
    exit 1
}
