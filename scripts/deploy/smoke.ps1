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
    $origin = [Uri]$BaseUrl
    if ($origin.Scheme -ne "https" -or -not $origin.Host -or $origin.AbsolutePath -notin @("", "/") -or $origin.Query) {
        throw "Preview smoke requires one public HTTPS web origin."
    }
    $previewSmoke = & $PythonExecutable -m umbral.ops.smoke preview --base-url $BaseUrl --manifest-path $manifestFullPath | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $previewSmoke.passed) { throw "Preview identity smoke failed." }
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
