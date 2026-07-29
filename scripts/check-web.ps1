[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$webRoot = Join-Path $repoRoot "apps\web"
$webPackage = Join-Path $webRoot "package.json"
$lockfile = Join-Path $repoRoot "package-lock.json"
$nodeModules = Join-Path $repoRoot "node_modules"

foreach ($requiredPath in @($webPackage, $lockfile, $nodeModules)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Web surface detectada pero falta el prerequisito requerido: $requiredPath"
    }
}

function Get-CommandPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $commands = @(Get-Command $Name -All -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandType -in @("Application", "ExternalScript") })
    $command = $commands |
        Where-Object { $_.Source -match '\.cmd$' } |
        Select-Object -First 1
    if ($null -eq $command) {
        $command = $commands | Select-Object -First 1
    }
    if ($null -eq $command) {
        throw "Web surface detectada pero no se encontro '$Name' en PATH. Instala Node 24 y npm 12, y vuelve a ejecutar el harness."
    }
    return $command.Source
}

function Get-ToolVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $Executable --version 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $versionText = ($output -join "`n").Trim()
    if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($versionText)) {
        throw "No se pudo obtener la version de $Name desde '$Executable'. Salida: $versionText"
    }

    $match = [regex]::Match($versionText, '(?m)^\s*v?(\d+)\.(\d+)\.(\d+)')
    if (-not $match.Success) {
        throw "La salida de $Name no contiene una version semver reconocible: $versionText"
    }

    return [pscustomobject]@{
        Text  = $versionText
        Major = [int]$match.Groups[1].Value
        Minor = [int]$match.Groups[2].Value
        Patch = [int]$match.Groups[3].Value
    }
}

function Invoke-NpmCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ("[CHECK] Web {0}" -f $Name)
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $npmPath @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw ("Web {0} termino con codigo {1}." -f $Name, $exitCode)
    }
}

$nodePath = Get-CommandPath -Name "node"
$npmPath = Get-CommandPath -Name "npm"
$nodeVersion = Get-ToolVersion -Executable $nodePath -Name "Node.js"
$npmVersion = Get-ToolVersion -Executable $npmPath -Name "npm"

if ($nodeVersion.Major -ne 24 -or $nodeVersion.Minor -lt 11) {
    throw "Se requiere Node.js >=24.11,<25; se encontro $($nodeVersion.Text). Activa una version compatible y vuelve a ejecutar el harness."
}
if ($npmVersion.Major -ne 12) {
    throw "Se requiere npm >=12,<13; se encontro $($npmVersion.Text). Activa npm 12 y vuelve a ejecutar el harness."
}

$requiredBinaries = @("eslint", "tsc", "vitest", "playwright")
foreach ($binary in $requiredBinaries) {
    $binaryPath = Join-Path $nodeModules ".bin\$binary"
    if (-not (Test-Path -LiteralPath $binaryPath)) {
        throw "Faltan dependencias web instaladas: no existe node_modules/.bin/$binary. Ejecuta npm ci con el lockfile."
    }
}

Push-Location $repoRoot
try {
    Invoke-NpmCheck -Name "dependencias del workspace" -Arguments @("ls", "--workspace", "@umbral/web", "--depth=0", "--include=dev")
    Invoke-NpmCheck -Name "lint" -Arguments @("run", "lint", "--workspace", "@umbral/web")
    Invoke-NpmCheck -Name "typecheck" -Arguments @("run", "typecheck", "--workspace", "@umbral/web")
    Invoke-NpmCheck -Name "Vitest" -Arguments @("run", "test", "--workspace", "@umbral/web", "--", "--passWithNoTests")
    Invoke-NpmCheck -Name "coleccion Playwright" -Arguments @("run", "test:e2e", "--workspace", "@umbral/web", "--", "--list", "--pass-with-no-tests")
}
finally {
    Pop-Location
}

Write-Host "[PASS] Checks web (ESLint, TypeScript, Vitest y coleccion Playwright)"
exit 0
