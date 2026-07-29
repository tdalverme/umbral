[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$sourceRoots = @(
    (Join-Path $repoRoot "src\umbral"),
    (Join-Path $repoRoot "umbral")
) | Where-Object { Test-Path -LiteralPath $_ }

if ($sourceRoots.Count -eq 0) {
    Write-Host "[SKIP] Arquitectura: todavia no existe el paquete umbral."
    return
}

$rules = @(
    @{
        Layer = "domain"
        Pattern = "(?im)^\s*(from|import)\s+(fastapi|sqlalchemy|sqlmodel|openai|(?:src\.)?umbral\.(api|infrastructure|workers|agent))"
        Message = "domain no puede depender de framework, DB, LLM, API, workers ni agent"
    },
    @{
        Layer = "application"
        Pattern = "(?im)^\s*(from|import)\s+(fastapi|(?:src\.)?umbral\.(api|infrastructure))"
        Message = "application no puede depender de API ni infraestructura"
    },
    @{
        Layer = "agent"
        Pattern = "(?im)^\s*(from|import)\s+(sqlalchemy|sqlmodel|(?:src\.)?umbral\.infrastructure\.db)"
        Message = "agent no puede acceder directamente a DB"
    }
)

$violations = [System.Collections.Generic.List[string]]::new()
foreach ($sourceRoot in $sourceRoots) {
    $files = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Filter "*.py"
    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($sourceRoot.Length + 1)
        $layer = ($relativePath -split "[\\/]")[0]
        $content = Get-Content -LiteralPath $file.FullName -Raw

        foreach ($rule in $rules | Where-Object { $_.Layer -eq $layer }) {
            if ($content -match $rule.Pattern) {
                $violations.Add(("{0}: {1}" -f $file.FullName, $rule.Message))
            }
        }
    }
}

if ($violations.Count -gt 0) {
    throw ($violations -join [Environment]::NewLine)
}

Write-Host "[PASS] Direccion de dependencias"
