[CmdletBinding()]
param([string]$PolicyPath = "infra\cloudflare\access-policy.json")

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$policyFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PolicyPath))
$policy = Get-Content -Raw -LiteralPath $policyFullPath | ConvertFrom-Json
$expectedPublicPaths = @(
    "/health",
    "/login",
    "/auth/capture",
    "/auth/confirm",
    "/api/auth/magic-link-requests",
    "/api/webhooks/email"
)
$actualPublicPaths = @($policy.public_paths)
if ($actualPublicPaths.Count -ne $expectedPublicPaths.Count -or (Compare-Object $actualPublicPaths $expectedPublicPaths)) {
    throw "Access policy must use the exact anonymous environment-path allowlist."
}
if ($policy.access_mode -ne "product_session") {
    throw "Access policy must select product_session for beta."
}
if (-not $policy.origin_closed -or -not $policy.web_public_domain -or $policy.api_public_domain -or -not $policy.datastores_private_or_managed -or -not $policy.umbral_session_protection) {
    throw "Access policy must close origin, expose only web, keep the API and datastores private, and enable Umbral sessions."
}
if (-not $policy.webhook_anonymous_at_environment_gate -or -not $policy.webhook_requires_provider_signature) {
    throw "Email webhook must be anonymous only at the environment gate and require provider verification."
}
[ordered]@{
    policy = $PolicyPath
    access_mode = $policy.access_mode
    web_public_domain = [bool]$policy.web_public_domain
    api_public_domain = [bool]$policy.api_public_domain
    datastores_private_or_managed = [bool]$policy.datastores_private_or_managed
    umbral_session_protection = [bool]$policy.umbral_session_protection
    public_paths = @($policy.public_paths)
    credentials_observed = $false
} | ConvertTo-Json -Depth 5
