[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$sourceRoot = Join-Path $repoRoot "src\umbral"
$architectureTest = Join-Path $repoRoot "tests\architecture\test_dependency_rules.py"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$lintPath = Join-Path $repoRoot ".venv\Scripts\lint-imports.exe"

foreach ($requiredPath in @($sourceRoot, $architectureTest, $pythonPath, $lintPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        Write-Error ("[FAIL] Arquitectura: falta el prerequisito requerido: {0}" -f $requiredPath)
        exit 2
    }
}

Push-Location $repoRoot
try {
    Write-Host "[CHECK] Fixtures de arquitectura"
    & $pythonPath -m pytest $architectureTest -q
    $pytestExitCode = $LASTEXITCODE
    if ($pytestExitCode -ne 0) {
        Write-Error ("[FAIL] Fixtures de arquitectura: pytest termino con codigo {0}" -f $pytestExitCode)
        exit $pytestExitCode
    }

    $previousPythonPath = $env:PYTHONPATH
    try {
        $srcPath = Join-Path $repoRoot "src"
        if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
            $env:PYTHONPATH = $srcPath
        }
        else {
            $env:PYTHONPATH = $srcPath + [System.IO.Path]::PathSeparator + $previousPythonPath
        }

        Write-Host "[CHECK] Contratos Import Linter"
        & $lintPath --no-cache --verbose
        $lintExitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousPythonPath) {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONPATH = $previousPythonPath
        }
    }

    if ($lintExitCode -ne 0) {
        Write-Error ("[FAIL] Contratos Import Linter: lint-imports termino con codigo {0}" -f $lintExitCode)
        exit $lintExitCode
    }
}
finally {
    Pop-Location
}

Write-Host "[PASS] Direccion de dependencias"
exit 0
