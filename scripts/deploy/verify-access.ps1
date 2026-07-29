[CmdletBinding()]
param([string]$PolicyPath = "infra\cloudflare\access-policy.json")

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$policyFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PolicyPath))
$policy = Get-Content -Raw -LiteralPath $policyFullPath | ConvertFrom-Json
if ($policy.public_paths.Count -ne 1 -or $policy.public_paths[0] -ne "/health") {
    throw "Access policy must expose only the exact /health path."
}
if (-not $policy.origin_closed -or -not $policy.datastores_private -or -not $policy.require_access) {
    throw "Access policy must close origin and keep datastores private."
}
[ordered]@{
    policy = $PolicyPath
    origin_closed = [bool]$policy.origin_closed
    datastores_private = [bool]$policy.datastores_private
    public_paths = @($policy.public_paths)
    credentials_observed = $false
} | ConvertTo-Json -Depth 5
