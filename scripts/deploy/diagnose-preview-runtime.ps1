[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$PythonExecutable,
    [Parameter(Mandatory = $true)] [string]$ManifestPath
)

$ErrorActionPreference = "Stop"

# The promote job carries runner-only variables (release metadata, smoke
# fixtures, preview URL) that Settings validation would reject as unknown and
# lacks the static preview service variables. Drop the former and set the latter
# so the diagnostics reproduce the deployed service environment, backed by the
# runner's reachable resource URLs for real scheduler/worker passes.
Get-ChildItem Env: | Where-Object {
    $_.Name -eq "UMBRAL_MANIFEST_DATABASE_REVISION" -or
    $_.Name -eq "UMBRAL_PREVIEW_BASE_URL" -or
    $_.Name -like "UMBRAL_SMOKE_*"
} | Remove-Item

$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$manifestJson = [string](Get-Content -Raw -LiteralPath $ManifestPath)

$env:UMBRAL_ENV = "preview"
$env:UMBRAL_RELEASE_ID = [string]$manifest.release_id
$env:UMBRAL_RELEASE_DIGEST = [string]$manifest.artifacts.runtime.digest
$env:UMBRAL_RELEASE_MANIFEST = $manifestJson
$env:UMBRAL_ACCESS_MODE = "product_session"
$env:UMBRAL_API_BASE_URL = "http://api.railway.internal"
$env:UMBRAL_BFF_TOKEN = ""
$env:SESSION_COOKIE_NAME = "__Host-umbral_session"
$env:SESSION_SECURE = "true"
$env:IDENTITY_PROVIDER = "supabase"
$env:EMAIL_PROVIDER = "resend"
$env:OBJECT_STORE_BACKEND = "s3"
$env:IDENTITY_FINGERPRINT_KEY = "preview-identity-fingerprint-key-diagnostic"
$env:IDENTITY_CAPTURE_ORIGIN = "https://umbral-preview.example.invalid"
if ([string]::IsNullOrWhiteSpace([string]$env:EMAIL_WEBHOOK_SECRET)) {
    $env:EMAIL_WEBHOOK_SECRET = "diagnostic-email-webhook-secret"
}
if ([string]$env:REDIS_URL -match "^redis://") {
    $env:REDIS_URL = $env:REDIS_URL -replace "^redis://", "rediss://"
}

# Reproduce the scheduler service boot and the api runtime composition on the
# promote runner so failures surface with a full traceback instead of the
# swallowed "scheduler-once failed" line.

$schedulerCode = @'
from umbral.workers.composition import build_process_dependencies
from umbral.workers.scheduler import scheduler_once, DEFAULT_DUE_WORK_LIMIT
deps = build_process_dependencies()
summary = scheduler_once(
    deps.runtime,
    queue=deps.queue,
    identity_store=deps.identity_store,
    limit=DEFAULT_DUE_WORK_LIMIT,
)
print("scheduler-once summary:", summary)
'@

$apiCode = @'
from umbral.api.dependencies import build_runtime_dependencies
deps = build_runtime_dependencies()
print("api runtime composition boot OK; release_id:", deps.release.release_id)
'@

$workerCode = @'
from umbral.workers.composition import build_process_dependencies
deps = build_process_dependencies()
print("worker composition boot OK; engine drivername:", deps.session_provider.engine.url.drivername)
'@

$apiAppCode = @'
import umbral.api.main
from umbral.api.main import app
print("api app module import OK; title:", app.title)
'@

function Invoke-Diagnostic([string]$Label, [string]$Code) {
    Write-Host ""
    Write-Host "=== $Label ==="
    & $PythonExecutable -c $Code
    if ($LASTEXITCODE -eq 0) {
        Write-Host "$Label OK"
    } else {
        Write-Host "$Label FAILED (exit $LASTEXITCODE)"
    }
}

# Dump the live Railway api service configuration so the promote log shows the
# exact start command, healthcheck and variables Railway applies to the api.
function Dump-LiveApiServiceConfig {
    Write-Host ""
    Write-Host "=== live api service config ==="
    try {
        $rawConfig = & npx @railway/cli@5.27.2 environment config -e preview --json
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($rawConfig)) {
            Write-Host "environment config failed (exit $LASTEXITCODE)"
            return
        }
        $config = $rawConfig | ConvertFrom-Json
        $rawStatus = & npx @railway/cli@5.27.2 service status --all -e preview --json
        $serviceId = $null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($rawStatus)) {
            $serviceId = [string](($rawStatus | ConvertFrom-Json) | Where-Object { $_.name -eq "api" } | Select-Object -First 1).id
        }
        if (-not $serviceId) {
            Write-Host "api service id not found"
            return
        }
        $apiConfig = $config.services.$serviceId
        if ($null -eq $apiConfig) {
            Write-Host "api service config not found"
            return
        }
        Write-Host "api service id: $serviceId"
        $apiConfig | ConvertTo-Json -Depth 8
    } catch {
        Write-Host ("live api service config dump failed: {0}" -f $_.Exception.Message)
    }
}

Invoke-Diagnostic "scheduler-once (composition + one pass)" $schedulerCode
Invoke-Diagnostic "worker composition boot" $workerCode
Invoke-Diagnostic "api runtime composition boot" $apiCode
Invoke-Diagnostic "api app module import (uvicorn path)" $apiAppCode
Dump-LiveApiServiceConfig
exit 0
