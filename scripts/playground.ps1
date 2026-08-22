param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "No encontré .venv\Scripts\python.exe. Creá el entorno local antes de iniciar el playground."
}

$env:PYTHONPATH = Join-Path $repoRoot "src"
$env:UMBRAL_API_BASE_URL = "http://127.0.0.1:$ApiPort"
$env:UMBRAL_PRIVATE_API_URL = "http://127.0.0.1:$ApiPort"
$env:UMBRAL_BFF_TOKEN = "local-bff-token"
$env:UMBRAL_ACCESS_MODE = "product_session"
$next = Join-Path $repoRoot "node_modules\.bin\next.cmd"

if (-not (Test-Path -LiteralPath $next)) {
    throw "Faltan dependencias web instaladas: no existe node_modules/.bin/next.cmd. Ejecuta npm ci con el lockfile."
}

$apiProcess = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "umbral.api.playground_main:app", "--reload", "--port", "$ApiPort") `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Playground API: http://127.0.0.1:$ApiPort"
Write-Host "Playground web: http://localhost:$WebPort/playground"
Write-Host "Fake mode: disponible sin credenciales. Real mode: requiere AGENT_MANAGED_ENDPOINT y AGENT_MANAGED_API_KEY."
Write-Host "No se inicia Postgres, Redis, workers, scheduler, release ni harness."

try {
    Push-Location (Join-Path $repoRoot "apps\web")
    & $next dev --port $WebPort
}
finally {
    Pop-Location
    if (-not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id
    }
}
