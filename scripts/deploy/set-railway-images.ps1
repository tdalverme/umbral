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

function Get-DeploymentId($Value) {
    if ($Value -isnot [pscustomobject]) { return $null }
    $properties = @($Value.PSObject.Properties.Name)
    if ($properties.Count -ne 1 -or $properties[0] -notin @("deploymentId", "deployment_id")) {
        return $null
    }
    $deploymentId = [string]$Value.($properties[0])
    if ([string]::IsNullOrWhiteSpace($deploymentId)) { return $null }
    return $deploymentId
}

if ([string]::IsNullOrWhiteSpace($env:RAILWAY_TOKEN) -and [string]::IsNullOrWhiteSpace($env:RAILWAY_API_TOKEN)) {
    throw "A sealed Railway project or workspace token is required."
}
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Release manifest was not found." }

$manifestFullPath = [System.IO.Path]::GetFullPath($ManifestPath)
$actualChecksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
Require-Condition ($ManifestSha256 -match "^[0-9a-f]{64}$") "Manifest checksum must be a lowercase sha256 value."
Require-Condition ($actualChecksum -eq $ManifestSha256) "Release manifest checksum does not match."

$manifestJson = Get-Content -Raw -LiteralPath $manifestFullPath
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
$deploymentIds = [ordered]@{}
foreach ($service in $serviceArtifacts.Keys) {
    $artifact = $manifest.artifacts.($serviceArtifacts[$service])
    $imageReference = "{0}@{1}" -f $artifact.image, $artifact.digest
    $response = & npx @railway/cli@5.27.2 environment edit -e $Environment `
        --service-config $service source.image $imageReference `
        --service-config $service variables.UMBRAL_RELEASE_ID.value $manifest.release_id `
        --service-config $service variables.UMBRAL_RELEASE_DIGEST.value $artifact.digest `
        --service-config $service variables.UMBRAL_RELEASE_MANIFEST.value $manifestJson `
        -m $manifest.release_id --json
    if ($LASTEXITCODE -ne 0) { throw ("Railway image update failed for {0}." -f $service) }
    $deploymentId = Get-DeploymentId ($response | ConvertFrom-Json)
    if ([string]::IsNullOrWhiteSpace($deploymentId)) {
        Write-Host "Railway CLI response for ${service}:"
        Write-Host ($response | Out-String)
        throw ("Railway returned an ambiguous deployment ID for {0}." -f $service)
    }
    $deploymentIds[$service] = $deploymentId
}

[ordered]@{
    release_id = $manifest.release_id
    manifest_sha256 = $actualChecksum
    deployment_ids = $deploymentIds
} | ConvertTo-Json -Depth 5
