[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$issues = [System.Collections.Generic.List[string]]::new()

$requiredFiles = @(
    "AGENTS.md",
    "docs\architecture\overview.md",
    "docs\api\endpoints.md",
    ".specify\memory\constitution.md"
)

foreach ($relativePath in $requiredFiles) {
    $path = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $path)) {
        $issues.Add("Falta $relativePath")
    }
}

$agentsPath = Join-Path $repoRoot "AGENTS.md"
if (Test-Path -LiteralPath $agentsPath) {
    $agentsLines = @(Get-Content -LiteralPath $agentsPath)
    if ($agentsLines.Count -gt 60) {
        $issues.Add("AGENTS.md tiene $($agentsLines.Count) lineas; el limite es 60")
    }
    $agentsContent = Get-Content -LiteralPath $agentsPath -Raw
    if ($agentsContent -notmatch "scripts\\check\.ps1") {
        $issues.Add("AGENTS.md no documenta .\\scripts\\check.ps1")
    }
}

$constitutionPath = Join-Path $repoRoot ".specify\memory\constitution.md"
if (Test-Path -LiteralPath $constitutionPath) {
    $constitution = Get-Content -LiteralPath $constitutionPath -Raw
    if ($constitution -match "\[[A-Z0-9_]+\]") {
        $issues.Add("La constitucion contiene placeholders sin resolver")
    }
}

$endpointsPath = Join-Path $repoRoot "docs\api\endpoints.md"
if (Test-Path -LiteralPath $endpointsPath) {
    $endpoints = Get-Content -LiteralPath $endpointsPath -Raw
    if ($endpoints -notmatch "\|\s*Metodo\s*\|\s*Ruta\s*\|\s*Recurso\s*\|\s*Proposito\s*\|\s*Estado\s*\|") {
        $issues.Add("docs/api/endpoints.md no contiene la tabla placeholder esperada")
    }
}

if ($issues.Count -gt 0) {
    throw ($issues -join [Environment]::NewLine)
}

Write-Host "[PASS] Documentacion y contratos"
