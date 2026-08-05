[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$ManifestSha256,
    [Parameter(Mandatory = $true)] [ValidateSet("preview", "production")] [string]$Environment
)

$ErrorActionPreference = "Stop"
$digestPattern = "^sha256:[0-9a-f]{64}$"

function Require-Condition([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Require-AllowedProperties($Value, [string[]]$Required, [string[]]$Allowed, [string]$Message) {
    $properties = @($Value.PSObject.Properties.Name)
    Require-Condition (@($properties | Where-Object { $_ -notin $Allowed }).Count -eq 0) $Message
    Require-Condition (@($Required | Where-Object { $_ -notin $properties }).Count -eq 0) $Message
}

function Get-RailwayDeploymentIds([string]$Service, [string]$Environment) {
    $raw = & npx @railway/cli@5.27.2 deployment list -e $Environment --service $Service --json
    if ($LASTEXITCODE -ne 0) { throw ("Railway deployment query failed for {0}." -f $Service) }
    if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
    $ids = @()
    foreach ($deployment in ($raw | ConvertFrom-Json)) {
        $ids += [string]$deployment.id
    }
    return $ids
}

if ([string]::IsNullOrWhiteSpace($env:RAILWAY_TOKEN) -and [string]::IsNullOrWhiteSpace($env:RAILWAY_API_TOKEN)) {
    throw "A sealed Railway project or workspace token is required."
}
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Release manifest was not found." }

$manifestFullPath = [System.IO.Path]::GetFullPath($ManifestPath)
$actualChecksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
Require-Condition ($ManifestSha256 -match "^[0-9a-f]{64}$") "Manifest checksum must be a lowercase sha256 value."
Require-Condition ($actualChecksum -eq $ManifestSha256) "Release manifest checksum does not match."

$manifestJson = [string](Get-Content -Raw -LiteralPath $manifestFullPath)
$manifest = $manifestJson | ConvertFrom-Json
$rootProperties = @($manifest.PSObject.Properties.Name | Sort-Object)
$expectedRootProperties = @("artifacts", "built_at", "config_schema_version", "contract_major", "database_revision", "git_sha", "release_id", "schema_version")
Require-Condition (($rootProperties -join ",") -eq ($expectedRootProperties -join ",")) "Release manifest schema is invalid."
Require-Condition ($manifest.schema_version -eq 1 -and $manifest.contract_major -eq 1) "Release manifest schema version is invalid."
Require-Condition ($manifest.git_sha -match "^[0-9a-f]{40}$") "Release manifest git SHA is invalid."
Require-Condition ($manifest.release_id -match "^[A-Za-z0-9._-]{1,100}$") "Release manifest release ID is invalid."
Require-Condition ($manifest.database_revision -is [string] -and $manifest.database_revision.Length -in 1..64) "Release manifest database revision is invalid."
try { [void][DateTimeOffset]::Parse($manifest.built_at) } catch { throw "Release manifest build time is invalid." }
Require-Condition (($manifest.config_schema_version -is [int] -or $manifest.config_schema_version -is [int64]) -and $manifest.config_schema_version -ge 1) "Release manifest config schema version is invalid."
Require-Condition ($null -ne $manifest.artifacts.web -and $null -ne $manifest.artifacts.runtime) "Release manifest artifacts are invalid."
Require-Condition ((@($manifest.artifacts.PSObject.Properties.Name | Sort-Object) -join ",") -eq "runtime,web") "Release manifest artifacts are invalid."

foreach ($artifactName in @("web", "runtime")) {
    $artifact = $manifest.artifacts.$artifactName
    Require-AllowedProperties $artifact @("image", "digest", "platform") @("image", "digest", "platform", "provenance") "Release manifest artifact schema is invalid."
    Require-Condition ($artifact.image -is [string] -and -not [string]::IsNullOrWhiteSpace($artifact.image)) "Release manifest image is invalid."
    Require-Condition ($artifact.digest -match $digestPattern) "Release manifest digest is invalid."
    Require-Condition ($artifact.platform -eq "linux/amd64") "Release manifest platform is invalid."
    if ($null -ne $artifact.provenance) {
        [Uri]$provenanceUri = $null
        Require-Condition ([Uri]::TryCreate($artifact.provenance, [UriKind]::Absolute, [ref]$provenanceUri)) "Release manifest provenance is invalid."
    }
}

$serviceArtifacts = [ordered]@{
    web = "web"
    api = "runtime"
    worker = "runtime"
    scheduler = "runtime"
}

# The api runtime binds uvicorn to port 8000; Railway probes the PORT variable
# to choose the healthcheck target port, so pin it explicitly to match.
$serviceExtraVars = @{
    api = [ordered]@{ PORT = "8000" }
}

# The stdin JSON path in `environment edit` does not translate service names to
# IDs; the backend only applies patches keyed by service ID, so resolve them here.
$rawStatus = & npx @railway/cli@5.27.2 service status --all -e $Environment --json
if ($LASTEXITCODE -ne 0) { throw "Railway service status query failed." }
$serviceIdByName = @{}
$statusByName = @{}
foreach ($svc in ($rawStatus | ConvertFrom-Json)) {
    $serviceIdByName[[string]$svc.name] = [string]$svc.id
    $statusByName[[string]$svc.name] = $svc
}
foreach ($service in $serviceArtifacts.Keys) {
    Require-Condition ($serviceIdByName.ContainsKey($service)) "Railway service '${service}' was not found in the environment."
}

# Preview runtimes require observability configuration; source it from the
# promote runner's secrets so the patch keeps every app service bootable.
$observabilityVars = [ordered]@{}
foreach ($key in @("OTEL_EXPORTER_OTLP_ENDPOINT", "SENTRY_DSN")) {
    $value = [Environment]::GetEnvironmentVariable($key)
    Require-Condition (-not [string]::IsNullOrWhiteSpace([string]$value)) "Missing ${key} environment value for Railway service variables."
    $observabilityVars[$key] = [string]$value
}
$otlpHeadersValue = [string][Environment]::GetEnvironmentVariable("OTEL_EXPORTER_OTLP_HEADERS")
if (-not [string]::IsNullOrWhiteSpace($otlpHeadersValue)) {
    $observabilityVars.OTEL_EXPORTER_OTLP_HEADERS = $otlpHeadersValue
}

# If the environment already pins this release, reuse the current deployment IDs
# and skip the (now idempotent) patch to avoid a no-op commit that yields no
# new deployment.
$currentConfigRaw = & npx @railway/cli@5.27.2 environment config -e $Environment --json
$alreadyAtTarget = $false
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($currentConfigRaw)) {
    $currentConfig = $currentConfigRaw | ConvertFrom-Json
    $alreadyAtTarget = $true
    foreach ($service in $serviceArtifacts.Keys) {
        $artifact = $manifest.artifacts.($serviceArtifacts[$service])
        $imageReference = "{0}@{1}" -f $artifact.image, $artifact.digest
        $svcConfig = $currentConfig.services.($serviceIdByName[$service])
        if ($null -eq $svcConfig -or $null -eq $svcConfig.source -or $null -eq $svcConfig.source.image -or [string]$svcConfig.source.image -ne $imageReference) { $alreadyAtTarget = $false; break }
        if ([string]$svcConfig.variables.UMBRAL_RELEASE_ID.value -ne [string]$manifest.release_id -or [string]$svcConfig.variables.UMBRAL_RELEASE_DIGEST.value -ne [string]$artifact.digest) { $alreadyAtTarget = $false; break }
        $storedManifest = $null
        try { $storedManifest = [string]$svcConfig.variables.UMBRAL_RELEASE_MANIFEST.value | ConvertFrom-Json } catch { $alreadyAtTarget = $false; break }
        if ($null -eq $storedManifest -or [string]$storedManifest.release_id -ne [string]$manifest.release_id -or [string]$storedManifest.git_sha -ne [string]$manifest.git_sha) { $alreadyAtTarget = $false; break }
        foreach ($key in $observabilityVars.Keys) {
            if ([string]$svcConfig.variables.$key.value -ne [string]$observabilityVars[$key]) { $alreadyAtTarget = $false; break }
        }
        if ($serviceExtraVars.ContainsKey($service)) {
            foreach ($key in $serviceExtraVars[$service].Keys) {
                if ([string]$svcConfig.variables.$key.value -ne [string]$serviceExtraVars[$service][$key]) { $alreadyAtTarget = $false; break }
            }
        }
    }
}
if ($alreadyAtTarget) {
    Write-Host "Environment already pinned to $($manifest.release_id); reusing current deployments."
    $currentDeploymentIds = [ordered]@{}
    foreach ($service in $serviceArtifacts.Keys) {
        $currentDeploymentIds[$service] = [string]$statusByName[$service].deploymentId
    }
    [ordered]@{
        release_id = $manifest.release_id
        manifest_sha256 = $actualChecksum
        deployment_ids = $currentDeploymentIds
    } | ConvertTo-Json -Depth 5
    return
}

$patch = [ordered]@{ services = [ordered]@{} }
foreach ($service in $serviceArtifacts.Keys) {
    $artifact = $manifest.artifacts.($serviceArtifacts[$service])
    $imageReference = "{0}@{1}" -f $artifact.image, $artifact.digest
    $serviceVariables = [ordered]@{
        UMBRAL_RELEASE_ID = [ordered]@{ value = $manifest.release_id }
        UMBRAL_RELEASE_DIGEST = [ordered]@{ value = $artifact.digest }
        UMBRAL_RELEASE_MANIFEST = [ordered]@{ value = $manifestJson }
        OTEL_EXPORTER_OTLP_ENDPOINT = [ordered]@{ value = $observabilityVars.OTEL_EXPORTER_OTLP_ENDPOINT }
        SENTRY_DSN = [ordered]@{ value = $observabilityVars.SENTRY_DSN }
    }
    if ($observabilityVars.Contains("OTEL_EXPORTER_OTLP_HEADERS")) {
        $serviceVariables.OTEL_EXPORTER_OTLP_HEADERS = [ordered]@{ value = $observabilityVars.OTEL_EXPORTER_OTLP_HEADERS }
    }
    if ($serviceExtraVars.ContainsKey($service)) {
        foreach ($key in $serviceExtraVars[$service].Keys) {
            $serviceVariables[$key] = [ordered]@{ value = $serviceExtraVars[$service][$key] }
        }
    }
    $patch.services[$serviceIdByName[$service]] = [ordered]@{
        source = [ordered]@{ image = $imageReference }
        variables = $serviceVariables
    }
}
$patchJson = $patch | ConvertTo-Json -Depth 6

$knownDeployments = @{}
foreach ($service in $serviceArtifacts.Keys) {
    $knownDeployments[$service] = @(Get-RailwayDeploymentIds -Service $service -Environment $Environment)
}

# The CLI ignores --service-config flags when stdin is not a terminal (CI),
# so the config patch is piped as stdin JSON and --json emits the result.
$response = $patchJson | & npx @railway/cli@5.27.2 environment edit -e $Environment -m $manifest.release_id --json
if ($LASTEXITCODE -ne 0) {
    Write-Host "Railway CLI response:"
    Write-Host ($response | Out-String)
    throw "Railway environment update failed."
}
$editResult = $response | ConvertFrom-Json
if ($editResult.committed -ne $true) {
    Write-Host "Railway CLI response:"
    Write-Host ($response | Out-String)
    throw "Railway environment update did not commit."
}

$deploymentIds = [ordered]@{}
foreach ($service in $serviceArtifacts.Keys) {
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    $deploymentId = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $ids = @(Get-RailwayDeploymentIds -Service $service -Environment $Environment)
        $known = @($knownDeployments[$service])
        foreach ($id in $ids) {
            if ($known -notcontains $id) { $deploymentId = $id; break }
        }
        if (-not [string]::IsNullOrWhiteSpace($deploymentId)) { break }
        Start-Sleep -Seconds 10
    }
    if ([string]::IsNullOrWhiteSpace($deploymentId)) {
        Write-Host "No new deployment detected for ${service}. Gathering Railway diagnostics..."
        $artifact = $manifest.artifacts.($serviceArtifacts[$service])
        Write-Host ("Target image: {0}@{1}" -f $artifact.image, $artifact.digest)
        try {
            $rawConfig = & npx @railway/cli@5.27.2 environment config -e $Environment --json
            if ($LASTEXITCODE -eq 0) {
                Write-Host "=== Environment config ==="
                Write-Host ($rawConfig | Out-String)
            } else {
                Write-Host "environment config failed (exit $LASTEXITCODE)"
            }
        } catch { Write-Host ("environment config failed: {0}" -f $_.Exception.Message) }
        try {
            $rawStatus = & npx @railway/cli@5.27.2 service status --all -e $Environment --json
            if ($LASTEXITCODE -eq 0) {
                Write-Host "=== Service status ==="
                Write-Host ($rawStatus | Out-String)
            } else {
                Write-Host "service status failed (exit $LASTEXITCODE)"
            }
        } catch { Write-Host ("service status failed: {0}" -f $_.Exception.Message) }
        try {
            $rawList = & npx @railway/cli@5.27.2 deployment list -e $Environment --service $service --json
            if ($LASTEXITCODE -eq 0) {
                Write-Host "=== Deployment list for ${service} ==="
                Write-Host ($rawList | Out-String)
            } else {
                Write-Host "deployment list failed (exit $LASTEXITCODE)"
            }
        } catch { Write-Host ("deployment list failed: {0}" -f $_.Exception.Message) }
        throw ("Railway did not create a new deployment for {0} after applying the image change." -f $service)
    }
    $deploymentIds[$service] = $deploymentId
    Write-Host "New deployment for ${service}: $deploymentId"
}

[ordered]@{
    release_id = $manifest.release_id
    manifest_sha256 = $actualChecksum
    deployment_ids = $deploymentIds
} | ConvertTo-Json -Depth 5
