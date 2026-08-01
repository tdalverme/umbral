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

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$pending = [System.Collections.Generic.HashSet[string]]::new([string[]]$services)
while ($pending.Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {
    foreach ($service in @($pending)) {
        $expectedId = [string]$deploymentIds.$service
        $deployments = & npx @railway/cli@5.27.2 deployment list -e $Environment --service $service --json
        if ($LASTEXITCODE -ne 0) { throw ("Railway deployment query failed for {0}." -f $service) }
        $deployment = @($deployments | ConvertFrom-Json | Where-Object { $_.id -eq $expectedId }) | Select-Object -First 1
        if ($null -eq $deployment) { continue }
        if ($deployment.status -eq "SUCCESS") {
            [void]$pending.Remove($service)
            continue
        }
        if ($deployment.status -in @("FAILED", "CRASHED", "REMOVED")) {
            throw ("Railway deployment {0} for {1} finished with {2}." -f $expectedId, $service, $deployment.status)
        }
    }
    if ($pending.Count -gt 0) { Start-Sleep -Seconds $PollSeconds }
}
if ($pending.Count -gt 0) {
    throw ("Timed out waiting for Railway deployments: {0}." -f ($pending -join ", "))
}

[ordered]@{ deployment_ids = $deploymentIds } | ConvertTo-Json -Depth 5
