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
# The web reaches the private api over Railway's internal DNS, which requires the
# container port; the provisioned UMBRAL_PRIVATE_API_URL must carry it.
$serviceExtraVars = @{
    api = [ordered]@{ PORT = "8000" }
    web = [ordered]@{ UMBRAL_PRIVATE_API_URL = "http://api.railway.internal:8000" }
}

# Preview app services that would otherwise sleep on idle, breaking the web->api
# calls the promotion smoke performs after the healthchecks (the api idles for
# ~10 minutes and the smoke runs later). Keep the HTTP-facing services awake.
$serviceDeployOverrides = @{
    web = [ordered]@{ sleepApplication = $false }
    api = [ordered]@{ sleepApplication = $false }
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

# The api runtime builds its S3 object store at composition time, so the deployed
# services need the object store variables sourced from the promote runner's
# secrets (same pattern as observability) to stay bootable.
$objectStoreVars = [ordered]@{
    OBJECT_STORE_BACKEND = [string][Environment]::GetEnvironmentVariable("OBJECT_STORE_BACKEND")
}
if ([string]::IsNullOrWhiteSpace($objectStoreVars.OBJECT_STORE_BACKEND)) {
    $objectStoreVars.OBJECT_STORE_BACKEND = "s3"
}
foreach ($key in @("OBJECT_STORE_BUCKET", "OBJECT_STORE_ENDPOINT_URL", "OBJECT_STORE_ACCESS_KEY", "OBJECT_STORE_SECRET_KEY")) {
    $value = [Environment]::GetEnvironmentVariable($key)
    Require-Condition (-not [string]::IsNullOrWhiteSpace([string]$value)) "Missing ${key} environment value for Railway service variables."
    $objectStoreVars[$key] = [string]$value
}

# Runtime services also need the current provider credentials so the worker can
# issue magic links; static provisioning can leave a rotated key behind, which
# makes the sender return 401 during the smoke. The magic-link capture URL must
# point at the public web origin, so the capture origin is derived from the
# promote runner's preview base URL instead of a stale static value.
$providerVars = [ordered]@{}
foreach ($key in @("RESEND_API_KEY", "RESEND_FROM_EMAIL", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "IDENTITY_ISSUER", "EMAIL_WEBHOOK_SECRET")) {
    $value = [Environment]::GetEnvironmentVariable($key)
    Require-Condition (-not [string]::IsNullOrWhiteSpace([string]$value)) "Missing ${key} environment value for Railway service variables."
    $providerVars[$key] = [string]$value
}
$previewBaseUrl = [string][Environment]::GetEnvironmentVariable("UMBRAL_PREVIEW_BASE_URL")
Require-Condition (-not [string]::IsNullOrWhiteSpace($previewBaseUrl)) "Missing UMBRAL_PREVIEW_BASE_URL environment value for Railway service variables."
$providerVars["IDENTITY_CAPTURE_ORIGIN"] = "https://" + $previewBaseUrl.Trim()

# Compare every app service against its target spec so only the services that
# actually diverge are patched. This keeps the promote idempotent (no-op when
# everything is already pinned) while still producing fresh deployments for the
# services that changed and reusing the current deployment IDs for the rest.
$currentConfig = $null
$currentConfigRaw = & npx @railway/cli@5.27.2 environment config -e $Environment --json
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($currentConfigRaw)) {
    $currentConfig = $currentConfigRaw | ConvertFrom-Json
}

function Test-ServiceAtTarget {
    param(
        [Parameter(Mandatory = $true)] [string]$Service,
        [Parameter(Mandatory = $true)] $Manifest,
        [Parameter(Mandatory = $true)] $ServiceArtifacts,
        [AllowNull()] $SvcConfig,
        [Parameter(Mandatory = $true)] $ObservabilityVars,
        [Parameter(Mandatory = $true)] $ObjectStoreVars,
        [Parameter(Mandatory = $true)] $ProviderVars,
        [Parameter(Mandatory = $true)] $ServiceDeployOverrides,
        [Parameter(Mandatory = $true)] $ServiceExtraVars
    )
    if ($null -eq $SvcConfig) { return $false }
    $artifact = $Manifest.artifacts.($ServiceArtifacts[$Service])
    $imageReference = "{0}@{1}" -f $artifact.image, $artifact.digest
    if ($null -eq $SvcConfig.source -or $null -eq $SvcConfig.source.image -or [string]$SvcConfig.source.image -ne $imageReference) { return $false }
    if ([string]$SvcConfig.variables.UMBRAL_RELEASE_ID.value -ne [string]$Manifest.release_id -or [string]$SvcConfig.variables.UMBRAL_RELEASE_DIGEST.value -ne [string]$artifact.digest) { return $false }
    $storedManifest = $null
    try { $storedManifest = [string]$SvcConfig.variables.UMBRAL_RELEASE_MANIFEST.value | ConvertFrom-Json } catch { return $false }
    if ($null -eq $storedManifest -or [string]$storedManifest.release_id -ne [string]$Manifest.release_id -or [string]$storedManifest.git_sha -ne [string]$Manifest.git_sha) { return $false }
    foreach ($key in $ObservabilityVars.Keys) {
        if ([string]$SvcConfig.variables.$key.value -ne [string]$ObservabilityVars[$key]) { return $false }
    }
    foreach ($key in $ObjectStoreVars.Keys) {
        if ([string]$SvcConfig.variables.$key.value -ne [string]$ObjectStoreVars[$key]) { return $false }
    }
    if ($Service -ne "web") {
        foreach ($key in $ProviderVars.Keys) {
            if ([string]$SvcConfig.variables.$key.value -ne [string]$ProviderVars[$key]) { return $false }
        }
    }
    if ($ServiceDeployOverrides.ContainsKey($Service)) {
        if ($null -eq $SvcConfig.deploy -or $null -eq $SvcConfig.deploy.sleepApplication -or [bool]$SvcConfig.deploy.sleepApplication -ne [bool]$ServiceDeployOverrides[$Service].sleepApplication) { return $false }
    }
    if ($ServiceExtraVars.ContainsKey($Service)) {
        foreach ($key in $ServiceExtraVars[$Service].Keys) {
            if ([string]$SvcConfig.variables.$key.value -ne [string]$ServiceExtraVars[$Service][$key]) { return $false }
        }
    }
    return $true
}

$serviceNeedsPatch = @{}
foreach ($service in $serviceArtifacts.Keys) {
    $svcConfig = $null
    if ($null -ne $currentConfig) {
        $svcConfig = $currentConfig.services.($serviceIdByName[$service])
    }
    $serviceNeedsPatch[$service] = -not (Test-ServiceAtTarget -Service $service -Manifest $manifest -ServiceArtifacts $serviceArtifacts -SvcConfig $svcConfig -ObservabilityVars $observabilityVars -ObjectStoreVars $objectStoreVars -ProviderVars $providerVars -ServiceDeployOverrides $serviceDeployOverrides -ServiceExtraVars $serviceExtraVars)
}

$servicesToPatch = @($serviceArtifacts.Keys | Where-Object { $serviceNeedsPatch[$_] })
if ($servicesToPatch.Count -eq 0) {
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
foreach ($service in $servicesToPatch) {
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
    foreach ($key in $ObjectStoreVars.Keys) {
        $serviceVariables[$key] = [ordered]@{ value = $ObjectStoreVars[$key] }
    }
    if ($service -ne "web") {
        foreach ($key in $ProviderVars.Keys) {
            $serviceVariables[$key] = [ordered]@{ value = $ProviderVars[$key] }
        }
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
    if ($serviceDeployOverrides.ContainsKey($service)) {
        # Reconstruct the full deploy object so sleepApplication flips without
        # dropping the start command, healthcheck or region configuration.
        $deployPatch = [ordered]@{}
        if ($null -ne $currentConfig) {
            $svcDeploySource = $currentConfig.services.($serviceIdByName[$service])
            if ($null -ne $svcDeploySource -and $null -ne $svcDeploySource.deploy) {
                $deployPatch = $svcDeploySource.deploy | ConvertTo-Json -Depth 12 | ConvertFrom-Json
            }
        }
        if ($deployPatch -is [System.Management.Automation.PSCustomObject]) {
            $deployPatch | Add-Member -NotePropertyName sleepApplication -NotePropertyValue $false -Force
        } else {
            $deployPatch = [ordered]@{ sleepApplication = $false }
        }
        $patch.services[$serviceIdByName[$service]].deploy = $deployPatch
    }
}
$patchJson = $patch | ConvertTo-Json -Depth 6

$knownDeployments = @{}
foreach ($service in $servicesToPatch) {
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
    if (-not $serviceNeedsPatch[$service]) {
        $deploymentIds[$service] = [string]$statusByName[$service].deploymentId
        Write-Host "Reusing deployment for ${service}: $($deploymentIds[$service])"
        continue
    }
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
