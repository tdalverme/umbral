[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [ValidateSet("preview", "production")] [string]$Environment,
    [Parameter(Mandatory = $true)] [string]$DeploymentIdsJson,
    [ValidateRange(1, 1800)] [int]$TimeoutSeconds = 600,
    [ValidateRange(1, 60)] [int]$PollSeconds = 10
)

$ErrorActionPreference = "Stop"
$deploymentIds = $DeploymentIdsJson | ConvertFrom-Json
$services = @("web", "api", "worker", "scheduler")
foreach ($service in $services) {
    if ([string]::IsNullOrWhiteSpace([string]$deploymentIds.$service)) {
        throw ("Missing deployment ID for {0}." -f $service)
    }
}

function Dump-DeploymentLogs([string]$Service, [string]$DeploymentId, [string]$Environment) {
    Write-Host "=== Deployment logs for $Service / $DeploymentId ==="
    try {
        $raw = & npx @railway/cli@5.27.2 logs --service $Service -e $Environment --lines 200 $DeploymentId 2>&1
        Write-Host ($raw | Out-String)
    } catch {
        Write-Host ("logs fetch failed: {0}" -f $_.Exception.Message)
    }
    try {
        $rawBuild = & npx @railway/cli@5.27.2 logs --build --service $Service -e $Environment --lines 200 $DeploymentId 2>&1
        if (-not [string]::IsNullOrWhiteSpace($rawBuild)) {
            Write-Host "=== Build logs for $Service / $DeploymentId ==="
            Write-Host ($rawBuild | Out-String)
        }
    } catch {
        Write-Host ("build logs fetch failed: {0}" -f $_.Exception.Message)
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$pending = [System.Collections.Generic.HashSet[string]]::new([string[]]$services)
$failures = [System.Collections.Generic.List[string]]::new()
while ($pending.Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {
    foreach ($service in @($pending)) {
        $expectedId = [string]$deploymentIds.$service
        $raw = & npx @railway/cli@5.27.2 deployment list -e $Environment --service $service --json
        if ($LASTEXITCODE -ne 0) { throw ("Railway deployment query failed for {0}." -f $service) }
        if ([string]::IsNullOrWhiteSpace($raw)) { continue }
        $ids = @()
        $statuses = @()
        foreach ($deployment in ($raw | ConvertFrom-Json)) {
            $ids += [string]$deployment.id
            $statuses += [string]$deployment.status
        }
        $deploymentIndex = [Array]::IndexOf($ids, $expectedId)
        if ($deploymentIndex -lt 0) { continue }
        $deploymentStatus = $statuses[$deploymentIndex]
        if ($deploymentStatus -in @("SUCCESS", "SLEEPING")) {
            [void]$pending.Remove($service)
            continue
        }
        if ($deploymentStatus -in @("FAILED", "CRASHED", "REMOVED", "SKIPPED", "CANCELED", "CANCELLED", "ERROR")) {
            $failures.Add(("{0} ({1}) finished with {2}" -f $service, $expectedId, $deploymentStatus))
            [void]$pending.Remove($service)
        }
    }
    if ($pending.Count -gt 0) { Start-Sleep -Seconds $PollSeconds }
}
if ($failures.Count -gt 0) {
    foreach ($failure in $failures) {
        Write-Host "FAILED: $failure"
    }
    foreach ($service in $services) {
        $expectedId = [string]$deploymentIds.$service
        $isFailed = $false
        foreach ($failure in $failures) {
            if ($failure -like "$service (*") { $isFailed = $true; break }
        }
        if ($isFailed) {
            Dump-DeploymentLogs -Service $service -DeploymentId $expectedId -Environment $Environment
        }
    }
    throw ("Railway deployments failed: {0}." -f ($failures -join "; "))
}
if ($pending.Count -gt 0) {
    throw ("Timed out waiting for Railway deployments: {0}." -f ($pending -join ", "))
}

[ordered]@{ deployment_ids = $deploymentIds } | ConvertTo-Json -Depth 5
