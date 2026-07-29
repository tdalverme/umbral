[CmdletBinding()]
param([string]$PolicyPath = "infra\cloudflare\access-policy.json")

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$policyFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PolicyPath))
$policy = Get-Content -Raw -LiteralPath $policyFullPath | ConvertFrom-Json
foreach ($requiredPath in @("/health", "/login", "/auth/capture", "/auth/confirm", "/api/auth/magic-link-requests")) {
    if ($policy.public_paths -notcontains $requiredPath) {
        throw "Access policy is missing anonymous identity path: $requiredPath"
    }
}
if (-not $policy.origin_closed -or -not $policy.datastores_private -or -not $policy.umbral_session_protection) {
    throw "Access policy must close origin, keep datastores private, and enable Umbral sessions."
}
[ordered]@{
    policy = $PolicyPath
    origin_closed = [bool]$policy.origin_closed
    datastores_private = [bool]$policy.datastores_private
    umbral_session_protection = [bool]$policy.umbral_session_protection
    public_paths = @($policy.public_paths)
    credentials_observed = $false
} | ConvertTo-Json -Depth 5
