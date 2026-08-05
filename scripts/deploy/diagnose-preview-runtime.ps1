[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$PythonExecutable,
    [Parameter(Mandatory = $true)] [string]$ManifestPath
)

$ErrorActionPreference = "Stop"

# Dump the shape of the smoke web origin without exposing the full URL value.
$previewBaseUrl = [string]$env:UMBRAL_PREVIEW_BASE_URL
if ([string]::IsNullOrWhiteSpace($previewBaseUrl)) {
    Write-Host "UMBRAL_PREVIEW_BASE_URL: <empty>"
} else {
    try {
        $origin = [Uri]$previewBaseUrl
        Write-Host ("UMBRAL_PREVIEW_BASE_URL origin: scheme={0} host={1} absolutePath='{2}' hasQuery={3} length={4}" -f $origin.Scheme, $origin.Host, $origin.AbsolutePath, ([bool]$origin.Query), $previewBaseUrl.Length)
    } catch {
        Write-Host "UMBRAL_PREVIEW_BASE_URL: unparsable"
    }
}

# The promote job carries runner-only variables (release metadata, smoke
# fixtures, preview URL) that Settings validation would reject as unknown and
# lacks the static preview service variables. Drop the former and set the latter
# so the diagnostics reproduce the deployed service environment, backed by the
# runner's reachable resource URLs for real scheduler/worker passes. This script
# runs in the same PowerShell process as the promote step, so the removed
# runner-only variables are restored afterwards for the preload and smoke steps.
$savedRunnerOnlyEnv = @{}
foreach ($name in @(Get-ChildItem Env: | Where-Object {
    $_.Name -eq "UMBRAL_MANIFEST_DATABASE_REVISION" -or
    $_.Name -eq "UMBRAL_PREVIEW_BASE_URL" -or
    $_.Name -like "UMBRAL_SMOKE_*"
} | ForEach-Object { $_.Name })) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($null -ne $value) { $savedRunnerOnlyEnv[$name] = $value }
    Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
}

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

# Run the real api boot (uvicorn + /health) inside the Railway environment so the
# deployed env is used verbatim (references resolved) rather than the runner's
# reconstruction. Best-effort: a failure here indicates the deployed env itself.
$apiRunCode = @'
import subprocess
import sys
import time
import urllib.request

from umbral.api.main import app  # noqa: F401

proc = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "umbral.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--log-level",
        "info",
    ],
)
try:
    deadline = time.time() + 45
    ok = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
                body = response.read().decode()
                print("health status:", response.status, body)
                ok = True
                break
        except Exception as error:
            time.sleep(1)
    print("health ok:", ok)
finally:
    proc.terminate()
    proc.wait(timeout=10)
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

function Invoke-RailwayRunDiagnostic {
    Write-Host ""
    Write-Host "=== api uvicorn + /health inside railway run ==="
    try {
        $scriptPath = Join-Path ([System.IO.Path]::GetTempPath()) "umbral-api-run-diagnostic.py"
        [System.IO.File]::WriteAllText($scriptPath, $apiRunCode, [Text.UTF8Encoding]::new($false))
        & npx @railway/cli@5.27.2 run -e preview --service api -- $PythonExecutable $scriptPath
        Write-Host "railway run api boot exit $LASTEXITCODE"
    } catch {
        Write-Host ("railway run api boot failed: {0}" -f $_.Exception.Message)
    }
}

# Dump the live Railway api service configuration so the promote log shows the
# exact start command, healthcheck and variables Railway applies to the api.
# Variable values are masked to keep secrets out of the workflow log.
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
        Write-Host ("environment config top-level properties: {0}" -f (@($config.PSObject.Properties.Name) -join ", "))
        Write-Host ("privateNetworkDisabled: {0}" -f $config.privateNetworkDisabled)
        $rawStatus = & npx @railway/cli@5.27.2 service status --all -e preview --json
        $serviceId = $null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($rawStatus)) {
            $serviceId = [string](($rawStatus | ConvertFrom-Json) | Where-Object { $_.name -eq "api" } | Select-Object -First 1).id
        }
        if (-not $serviceId) {
            Write-Host "api service id not found"
            return
        }
        Write-Host "api service id: $serviceId"
        $apiConfig = $null
        $servicesObject = $config.services
        if ($null -ne $servicesObject) {
            Write-Host ("services type: {0}" -f $servicesObject.GetType().FullName)
            if ($servicesObject -is [System.Array]) {
                $apiConfig = @($servicesObject) | Where-Object { $_.name -eq "api" } | Select-Object -First 1
            } else {
                $apiConfig = $servicesObject.$serviceId
                if ($null -eq $apiConfig) {
                    foreach ($prop in @($servicesObject.PSObject.Properties)) {
                        if ($null -ne $prop.Value -and $prop.Value.PSObject.Properties.Name -contains "name" -and [string]$prop.Value.name -eq "api") {
                            $apiConfig = $prop.Value
                            break
                        }
                    }
                }
            }
        }
        if ($null -eq $apiConfig) {
            Write-Host "api service config not found"
            return
        }
        Write-Host ("api service properties: {0}" -f (@($apiConfig.PSObject.Properties.Name) -join ", "))
        Write-Host "--- source ---"
        Write-Host ($apiConfig.source | ConvertTo-Json -Depth 5 -Compress)
        Write-Host "--- deploy ---"
        Write-Host ($apiConfig.deploy | ConvertTo-Json -Depth 10 -Compress)
        if ($null -ne $apiConfig.variables) {
            Write-Host ("--- variable names ({0}) ---" -f @($apiConfig.variables.PSObject.Properties.Name).Count)
            Write-Host (@($apiConfig.variables.PSObject.Properties.Name | Sort-Object) -join ", ")
        }
    } catch {
        Write-Host ("live api service config dump failed: {0}" -f $_.Exception.Message)
    }
}

function Dump-PreviewPublicDomains {
    Write-Host ""
    Write-Host "=== preview public domains ==="
    foreach ($attempt in @(
        @("domain list", "-e", "preview", "--json"),
        @("domain list", "-e", "preview"),
        @("service", "list", "-e", "preview", "--json")
    )) {
        try {
            Write-Host ("--- railway {0} ---" -f ($attempt -join " "))
            $raw = & npx @railway/cli@5.27.2 @attempt
            Write-Host ("exit {0}" -f $LASTEXITCODE)
            if (-not [string]::IsNullOrWhiteSpace($raw)) { Write-Host $raw }
        } catch {
            Write-Host ("failed: {0}" -f $_.Exception.Message)
        }
    }
}

# The web needs a private URL to reach the api, but the promote pipeline only
# pins image/release variables. Dump the live web/api internal URL variables
# (non-secret) so a misconfigured UMBRAL_PRIVATE_API_URL is visible in the log.
function Dump-PrivateApiUrlConfiguration {
    Write-Host ""
    Write-Host "=== web/api private api url configuration ==="
    foreach ($pair in @(
        @("web", "UMBRAL_PRIVATE_API_URL"),
        @("web", "UMBRAL_API_BASE_URL"),
        @("api", "UMBRAL_API_BASE_URL")
    )) {
        $service = $pair[0]
        $variable = $pair[1]
        try {
            $shellCommand = 'v="$' + $variable + '"; printf "%s (len %s)" "$v" "${#v}"'
            $value = & npx @railway/cli@5.27.2 run -e preview --service $service -- sh -c $shellCommand 2>&1
            Write-Host ("{0} {1} = {2}" -f $service, $variable, ($value -join " "))
        } catch {
            Write-Host ("{0} {1} query failed: {2}" -f $service, $variable, $_.Exception.Message)
        }
    }
    # The magic-link confirm verifies the Supabase access token issuer against
    # IDENTITY_ISSUER; report consistency with SUPABASE_URL without exposing
    # the project ref value.
    foreach ($service in @("api", "worker")) {
        try {
            $shellCommand = 'base="$SUPABASE_URL"; iss="$IDENTITY_ISSUER"; if [ "$iss" = "${base%/}/auth/v1" ]; then echo "consistent"; else echo "mismatch"; fi'
            $value = & npx @railway/cli@5.27.2 run -e preview --service $service -- sh -c $shellCommand 2>&1
            Write-Host ("{0} IDENTITY_ISSUER/supabase = {1}" -f $service, ($value -join " "))
        } catch {
            Write-Host ("{0} issuer check failed: {1}" -f $service, $_.Exception.Message)
        }
    }
    # BFF token presence without exposing the secret value.
    foreach ($service in @("web", "api")) {
        try {
            $shellCommand = 'v="$UMBRAL_BFF_TOKEN"; printf "len %s" "${#v}"'
            $value = & npx @railway/cli@5.27.2 run -e preview --service $service -- sh -c $shellCommand 2>&1
            Write-Host ("{0} UMBRAL_BFF_TOKEN {1}" -f $service, ($value -join " "))
        } catch {
            Write-Host ("{0} UMBRAL_BFF_TOKEN query failed: {1}" -f $service, $_.Exception.Message)
        }
    }
    # Redis endpoint shape per service (password masked) so a queue split
    # between the api/worker and the smoke relay is visible in the log.
    $runnerRedis = [string]$env:REDIS_URL
    if (-not [string]::IsNullOrWhiteSpace($runnerRedis)) {
        try {
            $runnerShape = & sh -c 'v="$1"; case "$v" in rediss://*) s="rediss";; *) s="redis";; esac; printf "%s://%s" "$s" "${v##*@}"' _ $runnerRedis 2>&1
            Write-Host ("runner REDIS_URL shape = {0}" -f ($runnerShape -join " "))
        } catch {
            Write-Host ("runner REDIS_URL shape query failed: {0}" -f $_.Exception.Message)
        }
    } else {
        Write-Host "runner REDIS_URL <empty>"
    }
    $shellCommand = 'v="$REDIS_URL"; case "$v" in rediss://*) s="rediss";; *) s="redis";; esac; printf "%s://%s" "$s" "${v##*@}"'
    foreach ($service in @("api", "worker")) {
        try {
            $value = & npx @railway/cli@5.27.2 run -e preview --service $service -- sh -c $shellCommand 2>&1
            Write-Host ("{0} REDIS_URL shape = {1}" -f $service, ($value -join " "))
        } catch {
            Write-Host ("{0} REDIS_URL query failed: {1}" -f $service, $_.Exception.Message)
        }
    }
    try {
        $shellCommand = 'printf "%s" "$UMBRAL_RELEASE_MANIFEST" | cut -c1-80; printf " (len %s)" "${#UMBRAL_RELEASE_MANIFEST}"'
        $value = & npx @railway/cli@5.27.2 run -e preview --service web -- sh -c $shellCommand 2>&1
        Write-Host ("web UMBRAL_RELEASE_MANIFEST prefix = {0}" -f ($value -join " "))
    } catch {
        Write-Host ("web UMBRAL_RELEASE_MANIFEST query failed: {0}" -f $_.Exception.Message)
    }
}

try {
    Invoke-Diagnostic "scheduler-once (composition + one pass)" $schedulerCode
    Invoke-Diagnostic "worker composition boot" $workerCode
    Invoke-Diagnostic "api runtime composition boot" $apiCode
    Invoke-Diagnostic "api app module import (uvicorn path)" $apiAppCode
    Invoke-RailwayRunDiagnostic
    Dump-LiveApiServiceConfig
    Dump-PrivateApiUrlConfiguration
    Dump-PreviewPublicDomains
} finally {
    foreach ($entry in $savedRunnerOnlyEnv.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value)
    }
}
exit 0
