[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$pythonProject = Join-Path $repoRoot "pyproject.toml"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonProject)) {
    throw "Python surface detectada pero falta pyproject.toml: $pythonProject"
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python surface detectada pero falta el interprete del entorno del repositorio: $pythonPath"
}

function Invoke-PythonCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ("[CHECK] Python {0}" -f $Name)
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $pythonPath @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw ("Python {0} termino con codigo {1}." -f $Name, $exitCode)
    }
}

Push-Location $repoRoot
try {
    Invoke-PythonCheck -Name "Ruff" -Arguments @("-m", "ruff", "check", "src", "tests")
    Invoke-PythonCheck -Name "mypy estricto" -Arguments @("-m", "mypy", "src", "tests")
    Invoke-PythonCheck -Name "pytest" -Arguments @("-m", "pytest")
}
finally {
    Pop-Location
}

Write-Host "[PASS] Checks Python (Ruff, mypy estricto y pytest)"
exit 0
