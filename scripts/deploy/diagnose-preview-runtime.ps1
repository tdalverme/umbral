[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"

# The promote job sets runner-only variables (release metadata, smoke fixtures,
# preview URL) that Settings validation would reject as unknown. Drop them so the
# diagnostics reproduce the deployed service environment instead of the runner's.
Get-ChildItem Env: | Where-Object {
    $_.Name -eq "UMBRAL_MANIFEST_DATABASE_REVISION" -or
    $_.Name -eq "UMBRAL_PREVIEW_BASE_URL" -or
    $_.Name -like "UMBRAL_SMOKE_*"
} | Remove-Item

# Reproduce the scheduler service boot and the api runtime composition on the
# promote runner (which carries the preview secrets) so failures surface with a
# full traceback instead of the swallowed "scheduler-once failed" line.

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
from umbral.workers.worker import build_rq_worker
deps = build_process_dependencies()
worker = build_rq_worker(deps.queue)
print("worker composition boot OK; worker:", type(worker).__name__)
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

Invoke-Diagnostic "scheduler-once (composition + one pass)" $schedulerCode
Invoke-Diagnostic "worker composition boot" $workerCode
Invoke-Diagnostic "api runtime composition boot" $apiCode
exit 0
