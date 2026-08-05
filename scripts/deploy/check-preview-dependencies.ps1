[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$EvidencePath,
    [string]$PythonExecutable
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Release manifest was not found." }

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $localPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $PythonExecutable = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}
$manifest = Get-Content -Raw -LiteralPath ([System.IO.Path]::GetFullPath($ManifestPath)) | ConvertFrom-Json
$evidenceFullPath = [System.IO.Path]::GetFullPath($EvidencePath)
$env:PYTHONPATH = Join-Path $repoRoot "src"
$env:UMBRAL_MANIFEST_DATABASE_REVISION = [string]$manifest.database_revision
$result = & $PythonExecutable -m umbral.ops.provider_conformance 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Preview dependency conformance failed:"
    Write-Host ($result | Out-String)
    throw "Preview dependency conformance failed."
}
$evidence = $result | Out-String | ConvertFrom-Json
if ($evidence.PSObject.Properties.Name -notcontains "passed" -or -not $evidence.passed) { throw "Preview dependency evidence is invalid." }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $evidenceFullPath) | Out-Null
[System.IO.File]::WriteAllText($evidenceFullPath, ($evidence | ConvertTo-Json -Compress -Depth 5) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
$evidence | ConvertTo-Json -Compress -Depth 5
