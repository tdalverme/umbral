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
        $global:LASTEXITCODE = 0
        & $Path
        $childSucceeded = $?
        $childExitCode = $LASTEXITCODE
        if ($null -eq $childExitCode) {
            $childExitCode = 0
        }
        if (-not $childSucceeded -or $childExitCode -ne 0) {
            throw ("El check hijo termino con codigo {0}." -f $childExitCode)
        }
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

    $pythonSurfacePaths = @(
        (Join-Path $repoRoot "pyproject.toml"),
        (Join-Path $repoRoot "src\umbral"),
        (Join-Path $repoRoot "tests")
    )
    $hasPythonSurface = $pythonSurfacePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($hasPythonSurface) {
        Invoke-ChildCheck -Name "Python" -Path (Join-Path $PSScriptRoot "check-python.ps1")
    }
    else {
        Write-Host "[SKIP] Python: no existe pyproject.toml, src\umbral ni tests\."
    }

    $migrationSurfacePaths = @(
        (Join-Path $repoRoot "alembic.ini"),
        (Join-Path $repoRoot "alembic"),
        (Join-Path $repoRoot "scripts\check-migrations.ps1")
    )
    $hasMigrationSurface = $migrationSurfacePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($hasMigrationSurface) {
        Invoke-ChildCheck -Name "Migraciones" -Path (Join-Path $PSScriptRoot "check-migrations.ps1")
    }
    else {
        Write-Host "[SKIP] Migraciones: no existe alembic.ini ni el directorio alembic\."
    }

    $jobsSurface = @(
        (Join-Path $repoRoot "src\umbral\application\jobs"),
        (Join-Path $repoRoot "tests\integration\jobs")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($jobsSurface) {
        Invoke-ChildCheck -Name "Jobs" -Path (Join-Path $PSScriptRoot "check-jobs.ps1")
    }

    $ingestionSurface = @(
        (Join-Path $repoRoot "src\umbral\application\ingestion"),
        (Join-Path $repoRoot "tests\integration\ingestion")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($ingestionSurface) {
        Invoke-ChildCheck -Name "Ingestion" -Path (Join-Path $PSScriptRoot "check-imports.ps1")
    }

    $silverSurface = @(
        (Join-Path $repoRoot "src\umbral\application\silver"),
        (Join-Path $repoRoot "tests\integration\silver")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($silverSurface) {
        Invoke-ChildCheck -Name "Silver" -Path (Join-Path $PSScriptRoot "check-silver.ps1")
    }

    $radarSurface = @(
        (Join-Path $repoRoot "src\umbral\application\radar"),
        (Join-Path $repoRoot "tests\integration\radar")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($radarSurface) {
        Invoke-ChildCheck -Name "Radar" -Path (Join-Path $PSScriptRoot "check-radar.ps1")
    }

    $storageSurface = @(
        (Join-Path $repoRoot "src\umbral\application\objects"),
        (Join-Path $repoRoot "tests\contract\test_object_store.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($storageSurface) {
        Invoke-ChildCheck -Name "Objetos" -Path (Join-Path $PSScriptRoot "check-storage.ps1")
    }

    $recoverySurface = @(
        (Join-Path $repoRoot "src\umbral\ops\backup.py"),
        (Join-Path $repoRoot "tests\integration\recovery")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($recoverySurface) {
        Invoke-ChildCheck -Name "Recuperacion" -Path (Join-Path $PSScriptRoot "check-recovery.ps1")
    }

    $releaseSurface = @(
        (Join-Path $repoRoot "contracts\release-manifest.schema.json"),
        (Join-Path $repoRoot "src\umbral\ops\release.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($releaseSurface) {
        Invoke-ChildCheck -Name "Release" -Path (Join-Path $PSScriptRoot "check-release.ps1")
    }

    $contractSurfacePaths = @(
        (Join-Path $repoRoot "contracts\openapi\v1\openapi.json"),
        (Join-Path $repoRoot "scripts\check-contracts.ps1"),
        (Join-Path $repoRoot "scripts\export-openapi.ps1")
    )
    $hasContractSurface = $contractSurfacePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($hasContractSurface) {
        Invoke-ChildCheck -Name "Contratos OpenAPI" -Path (Join-Path $PSScriptRoot "check-contracts.ps1")
    }
    else {
        Write-Host "[SKIP] Contratos OpenAPI: no existe el contrato publicado."
    }

    $webSurfacePaths = @(
        (Join-Path $repoRoot "apps\web"),
        (Join-Path $repoRoot "apps\web\package.json")
    )
    $hasWebSurface = $webSurfacePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($hasWebSurface) {
        Invoke-ChildCheck -Name "Web" -Path (Join-Path $PSScriptRoot "check-web.ps1")
    }
    else {
        Write-Host "[SKIP] Web: no existe apps\web ni apps\web\package.json."
    }

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
