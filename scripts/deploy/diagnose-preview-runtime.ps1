[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"

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
Invoke-Diagnostic "api runtime composition boot" $apiCode
exit 0
