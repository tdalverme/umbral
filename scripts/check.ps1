[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$failures = 0

function Invoke-ChildCheck {
    param(
        [string]$Name,
        [string]$Path
    )

    try {
        & $Path
    }
    catch {
        Write-Host ("[FAIL] {0}: {1}" -f $Name, $_.Exception.Message) -ForegroundColor Red
        $script:failures++
    }
}

Push-Location $repoRoot
try {
    Invoke-ChildCheck -Name "Documentacion" -Path (Join-Path $PSScriptRoot "check-docs.ps1")
    Invoke-ChildCheck -Name "Arquitectura" -Path (Join-Path $PSScriptRoot "check-architecture.ps1")

    $specifyPath = Join-Path $repoRoot ".venv\Scripts\specify.exe"
    if (Test-Path -LiteralPath $specifyPath) {
        try {
            & $specifyPath check
            $specifyExitCode = $LASTEXITCODE
            if ($specifyExitCode -ne 0) {
                throw "Spec Kit termino con codigo $specifyExitCode."
            }
            Write-Host "[PASS] Spec Kit"
        }
        catch {
            Write-Host ("[FAIL] Spec Kit: {0}" -f $_.Exception.Message) -ForegroundColor Red
            $failures++
        }
    }
    else {
        Write-Host "[SKIP] Spec Kit: .venv\Scripts\specify.exe no esta instalado."
    }

    $apiModulePaths = @(
        (Join-Path $repoRoot "src\umbral\api\main.py"),
        (Join-Path $repoRoot "umbral\api\main.py")
    )
    $hasApiModule = $apiModulePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($hasApiModule) {
        Invoke-ChildCheck -Name "API" -Path (Join-Path $PSScriptRoot "check-api.ps1")
    }
    else {
        Write-Host "[SKIP] API: todavia no existe umbral.api.main."
    }

    $testFiles = @()
    $testsPath = Join-Path $repoRoot "tests"
    if (Test-Path -LiteralPath $testsPath) {
        $testFiles = @(Get-ChildItem -LiteralPath $testsPath -Recurse -File -Filter "*.py")
    }

    if ($testFiles.Count -eq 0) {
        Write-Host "[SKIP] Tests: no hay archivos Python bajo tests\."
    }
    else {
        $pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path -LiteralPath $pythonPath)) {
            $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
            if ($pythonCommand) {
                $pythonPath = $pythonCommand.Source
            }
        }

        if (-not (Test-Path -LiteralPath $pythonPath) -and -not (Get-Command $pythonPath -ErrorAction SilentlyContinue)) {
            Write-Host "[SKIP] Tests: no hay Python disponible."
        }
        else {
            try {
                & $pythonPath -m pytest
                $pytestExitCode = $LASTEXITCODE
                if ($pytestExitCode -ne 0) {
                    throw "pytest termino con codigo $pytestExitCode."
                }
                Write-Host "[PASS] Tests"
            }
            catch {
                Write-Host ("[FAIL] Tests: {0}" -f $_.Exception.Message) -ForegroundColor Red
                $failures++
            }
        }
    }
}
finally {
    Pop-Location
}

if ($failures -gt 0) {
    Write-Host ("Harness finalizado con {0} fallo(s)." -f $failures) -ForegroundColor Red
    exit 1
}

Write-Host "Harness finalizado sin fallos bloqueantes." -ForegroundColor Green
exit 0
