[CmdletBinding()]
param([Parameter(Mandatory = $true)] [string]$ManifestPath)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ([System.IO.Path]::IsPathRooted($ManifestPath)) {
    $manifestFullPath = [System.IO.Path]::GetFullPath($ManifestPath)
} else {
    $manifestFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
}
$servicesPath = Join-Path $repoRoot "infra\railway\services.json"
$variablesPath = Join-Path $repoRoot "infra\railway\variables.example.json"
$digestPattern = "^sha256:[0-9a-f]{64}$"

function Require-Condition([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$servicesContract = Get-Content -Raw -LiteralPath $servicesPath | ConvertFrom-Json
$variableInventory = Get-Content -Raw -LiteralPath $variablesPath | ConvertFrom-Json

Require-Condition ($servicesContract.contract_version -eq 1) "Unsupported Railway services contract."
Require-Condition ($variableInventory.contract_version -eq 1) "Unsupported Railway variable inventory."
$services = @($servicesContract.services)
Require-Condition (@($services.name | Sort-Object) -join "," -eq "api,scheduler,web,worker") "Railway contract must define exactly web, api, worker, and scheduler."

$byName = @{}
foreach ($service in $services) { $byName[$service.name] = $service }

foreach ($service in $services) {
    Require-Condition ($null -ne $manifest.artifacts.($service.release_artifact)) ("Unknown release artifact for {0}." -f $service.name)
}

Require-Condition ($byName.web.release_artifact -eq "web") "Web must use the web release artifact."
Require-Condition ($byName.web.public_domain -eq $true) "Web must be the only public Railway service."
Require-Condition ($byName.web.healthcheck_path -eq "/health") "Web healthcheck must target /health."
Require-Condition ($byName.web.restart_policy -eq "ON_FAILURE") "Web restart policy must be ON_FAILURE."
Require-Condition ($byName.web.serverless_sleep -eq $true) "Web serverless sleep must be enabled."

Require-Condition ($byName.api.release_artifact -eq "runtime") "API must use the runtime release artifact."
Require-Condition ($byName.api.start_command -eq "python -m uvicorn umbral.api.main:app --host 0.0.0.0 --port 8000") "API start command is invalid."
Require-Condition ($byName.api.public_domain -eq $false) "API must remain private to Railway networking."
Require-Condition ($byName.api.healthcheck_path -eq "/health") "API healthcheck must target /health."
Require-Condition ($byName.api.restart_policy -eq "ON_FAILURE") "API restart policy must be ON_FAILURE."
Require-Condition ($byName.api.serverless_sleep -eq $true) "API serverless sleep must be enabled."

Require-Condition ($byName.worker.release_artifact -eq "runtime") "Worker must use the runtime release artifact."
Require-Condition ($byName.worker.start_command -eq "python -m umbral.workers worker") "Worker start command is invalid."
Require-Condition ($byName.worker.public_domain -eq $false) "Worker must remain private to Railway networking."
Require-Condition ($byName.worker.restart_policy -eq "ALWAYS") "Worker restart policy must be ALWAYS."
Require-Condition ($byName.worker.serverless_sleep -eq $false) "Worker serverless sleep must be disabled."

Require-Condition ($byName.scheduler.release_artifact -eq "runtime") "Scheduler must use the runtime release artifact."
Require-Condition ($byName.scheduler.start_command -eq "python -m umbral.workers scheduler-once") "Scheduler start command is invalid."
Require-Condition ($byName.scheduler.public_domain -eq $false) "Scheduler must not have a public domain."
Require-Condition ($byName.scheduler.restart_policy -eq "NEVER") "Scheduler restart policy must be NEVER."
Require-Condition ($byName.scheduler.cron_schedule -eq "*/5 * * * *") "Scheduler cron cadence must be at least five minutes."
Require-Condition ($byName.scheduler.cron_timezone -eq "UTC") "Scheduler cron timezone must be UTC."

foreach ($runtimeService in @("api", "worker", "scheduler")) {
    Require-Condition ($byName[$runtimeService].release_artifact -eq "runtime") ("{0} must share the runtime artifact." -f $runtimeService)
}
Require-Condition (@($services | Where-Object { $_.public_domain -eq $true }).Count -eq 1) "Only web may have a public domain."

$webDigest = $manifest.artifacts.web.digest
$runtimeDigest = $manifest.artifacts.runtime.digest
Require-Condition ($webDigest -match $digestPattern) "Web artifact digest must be immutable."
Require-Condition ($runtimeDigest -match $digestPattern) "Runtime artifact digest must be immutable."

foreach ($variable in @($variableInventory.variables)) {
    Require-Condition (@($variable.PSObject.Properties.Name | Sort-Object) -join "," -eq "name,scopes") "Variable inventory may contain only names and scopes."
    Require-Condition (-not [string]::IsNullOrWhiteSpace($variable.name)) "Variable inventory contains an empty name."
    Require-Condition (@($variable.scopes).Count -gt 0) ("Variable {0} has no scope." -f $variable.name)
}

Write-Output ("web={0}" -f $webDigest)
Write-Output ("runtime={0}" -f $runtimeDigest)
Write-Output "railway_contract=valid"
