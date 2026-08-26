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

    $criteriaSurface = @(
        (Join-Path $repoRoot "src\umbral\application\criteria"),
        (Join-Path $repoRoot "tests\integration\criteria")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($criteriaSurface) {
        Invoke-ChildCheck -Name "Criterios" -Path (Join-Path $PSScriptRoot "check-criteria.ps1")
    }

    $urbanSurface = @(
        (Join-Path $repoRoot "src\umbral\application\urban"),
        (Join-Path $repoRoot "tests\integration\urban")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($urbanSurface) {
        Invoke-ChildCheck -Name "Urban" -Path (Join-Path $PSScriptRoot "check-urban.ps1")
    }

    $scoringSurface = @(
        (Join-Path $repoRoot "src\umbral\application\scoring"),
        (Join-Path $repoRoot "tests\integration\scoring")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($scoringSurface) {
        Invoke-ChildCheck -Name "Scoring" -Path (Join-Path $PSScriptRoot "check-scoring.ps1")
    }

    $feedbackSurface = @(
        (Join-Path $repoRoot "src\umbral\application\feedback"),
        (Join-Path $repoRoot "tests\integration\feedback")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($feedbackSurface) {
        Invoke-ChildCheck -Name "Feedback" -Path (Join-Path $PSScriptRoot "check-feedback.ps1")
    }

    $spec019Surface = Join-Path $repoRoot "specs\019-spec-alignment\tasks.md"
    if (Test-Path -LiteralPath $spec019Surface) {
        Invoke-ChildCheck -Name "Spec 019" -Path (Join-Path $PSScriptRoot "check-019.ps1")
    }

    $matchingSurface = @(
        (Join-Path $repoRoot "src\umbral\application\matching"),
        (Join-Path $repoRoot "tests\contract\test_matching_golden.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($matchingSurface) {
        Invoke-ChildCheck -Name "Matching" -Path (Join-Path $PSScriptRoot "check-matching.ps1")
    }

    $agentSurface = @(
        (Join-Path $repoRoot "src\umbral\agent"),
        (Join-Path $repoRoot "tests\contract\test_agent_state_schema.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($agentSurface) {
        Invoke-ChildCheck -Name "Agent" -Path (Join-Path $PSScriptRoot "check-agent.ps1")
    }

    $agentToolsSurface = @(
        (Join-Path $repoRoot "src\umbral\agent\tools"),
        (Join-Path $repoRoot "tests\contract\test_agent_tools_contract.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($agentToolsSurface) {
        Invoke-ChildCheck -Name "Agent Tools" -Path (Join-Path $PSScriptRoot "check-agent-tools.ps1")
    }

    $chatSurface = @(
        (Join-Path $repoRoot "src\umbral\api\routers\chat.py"),
        (Join-Path $repoRoot "tests\contract\test_chat_streaming_contract.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($chatSurface) {
        Invoke-ChildCheck -Name "Chat Conversacional" -Path (Join-Path $PSScriptRoot "check-chat.ps1")
    }

    $agentEvalsSurface = @(
        (Join-Path $repoRoot "src\umbral\application\agent_evals"),
        (Join-Path $repoRoot "tests\contract\test_agent_evals_golden.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($agentEvalsSurface) {
        Invoke-ChildCheck -Name "Agent Evals" -Path (Join-Path $PSScriptRoot "check-evals.ps1")
    }

    $conversationV5Surface = @(
        (Join-Path $repoRoot "src\umbral\application\conversation\v5"),
        (Join-Path $repoRoot "contracts\agent\v5\context-schema-v5.json"),
        (Join-Path $repoRoot "tests\contract\test_agent_contracts_v5.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($conversationV5Surface) {
        $pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
        if (Test-Path -LiteralPath $pythonExe) {
            try {
                $global:LASTEXITCODE = 0
                $env:PYTHONPATH = Join-Path $repoRoot "src"
                & $pythonExe -m pytest @(
                    (Join-Path $repoRoot "tests\contract\test_agent_contracts_v5.py"),
                    (Join-Path $repoRoot "tests\contract\test_agent_evals_v4_contracts.py"),
                    (Join-Path $repoRoot "tests\unit\application\conversation\v5"),
                    (Join-Path $repoRoot "tests\unit\agent\intent\test_interpretation_v5.py"),
                    (Join-Path $repoRoot "tests\unit\agent\test_graph_v5.py"),
                    (Join-Path $repoRoot "tests\unit\application\agent_evals\v4")
                ) -q
                if ($LASTEXITCODE -ne 0) {
                    throw ("La suite Conversation V5 termino con codigo {0}." -f $LASTEXITCODE)
                }
                Write-Host "[PASS] Conversation V5" -ForegroundColor Green
            }
            catch {
                Write-Host ("[FAIL] Conversation V5: {0}" -f $_.Exception.Message) -ForegroundColor Red
                $script:failures++
            }
        }
        else {
            Write-Host "[SKIP] Conversation V5: no existe .venv\Scripts\python.exe."
        }
    }
    else {
        Write-Host "[SKIP] Conversation V5: no existe la superficie V5."
    }

    $notificationsSurface = @(
        (Join-Path $repoRoot "src\umbral\application\notifications"),
        (Join-Path $repoRoot "tests\contract\test_notifications_policy.py")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($notificationsSurface) {
        Invoke-ChildCheck -Name "Alertas Proactivas" -Path (Join-Path $PSScriptRoot "check-alerts.ps1")
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
