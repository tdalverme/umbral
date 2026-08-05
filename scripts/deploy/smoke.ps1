[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [ValidateSet("local", "preview")] [string]$Mode = "local",
    [string]$BaseUrl,
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $localPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $PythonExecutable = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}
$manifestFullPath = if ([System.IO.Path]::IsPathRooted($ManifestPath)) {
    [System.IO.Path]::GetFullPath($ManifestPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ManifestPath))
}
$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
foreach ($artifactName in @("web", "runtime")) {
    $artifact = $manifest.artifacts.$artifactName
    if ($artifact.platform -ne "linux/amd64" -or $artifact.digest -notmatch "^sha256:[0-9a-f]{64}$") {
        throw ("Invalid artifact in release manifest: {0}" -f $artifactName)
    }
}
$env:PYTHONPATH = Join-Path $repoRoot "src"
if ($Mode -eq "preview") {
    if ([string]::IsNullOrWhiteSpace($BaseUrl)) { throw "Preview smoke requires BaseUrl." }
    $BaseUrl = $BaseUrl.Trim()
    if ($BaseUrl -notmatch "^[a-zA-Z][a-zA-Z0-9+.-]*://") {
        $BaseUrl = "https://" + $BaseUrl
    }
    $origin = [Uri]$BaseUrl
    if ($origin.Scheme -ne "https" -or -not $origin.Host -or $origin.AbsolutePath -notin @("", "/") -or $origin.Query) {
        throw "Preview smoke requires one public HTTPS web origin."
    }
    $previewSmoke = & $PythonExecutable -m umbral.ops.smoke preview --base-url $BaseUrl --manifest-path $manifestFullPath | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $previewSmoke.passed) { throw "Preview identity smoke failed." }
    if (@($previewSmoke.PSObject.Properties.Name).Count -ne 2 -or @($previewSmoke.PSObject.Properties.Name | Where-Object { $_ -notin @("passed", "checks") }).Count -ne 0 -or $previewSmoke.passed -isnot [bool]) { throw "Preview smoke result schema is invalid." }
    $requiredScenarios = @("runtime_identity", "invitation", "invited", "scanner_prefetch", "explicit_confirmation", "single_use", "repeat", "non_invited", "authorization", "logout", "idle_expiry", "delivered", "bounced", "complained", "redaction")
    $checks = @($previewSmoke.checks)
    if ($checks.Count -ne $requiredScenarios.Count) { throw "Preview smoke has missing or duplicate scenarios." }
    $actualScenarios = @($checks | ForEach-Object { [string]$_.scenario })
    if ((@($actualScenarios | Select-Object -Unique)).Count -ne $requiredScenarios.Count -or @($requiredScenarios | Where-Object { $_ -notin $actualScenarios }).Count -ne 0) { throw "Preview smoke scenario set is invalid." }
    foreach ($check in $checks) {
        $keys = @($check.PSObject.Properties.Name)
        $requiredKeys = @("scenario", "code", "provider_id", "correlation_id", "observed_at", "duration_ms")
        if ($keys.Count -ne $requiredKeys.Count -or @($requiredKeys | Where-Object { $_ -notin $keys }).Count -ne 0) { throw "Preview smoke evidence schema is invalid." }
        if ([string]::IsNullOrWhiteSpace([string]$check.scenario) -or $check.code -ne "smoke.ok" -or [string]::IsNullOrWhiteSpace([string]$check.correlation_id) -or [string]::IsNullOrWhiteSpace([string]$check.observed_at) -or (-not ($check.duration_ms -is [int] -or $check.duration_ms -is [long])) -or $check.duration_ms -lt 0) { throw "Preview smoke check is invalid." }
    }
    $previewSmoke | ConvertTo-Json -Depth 8
    exit 0
}
$identitySmoke = & $PythonExecutable -m umbral.ops.smoke local | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $identitySmoke.result -ne "accepted") { throw "Identity smoke failed." }
[ordered]@{
    checks = @("web", "api", "worker", "scheduler", "extensions", "reference_job", "synthetic_object", "identity")
    release_id = $manifest.release_id
    manifest_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestFullPath).Hash.ToLowerInvariant()
    product_data_used = $false
    identity_smoke = $identitySmoke.result
} | ConvertTo-Json -Depth 5
