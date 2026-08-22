param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000,
    [string]$SnapshotPath = ""
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
$env:PLAYGROUND_SNAPSHOT_PATH = ""
$defaultSnapshotPath = Join-Path $repoRoot ".data\playground\real-snapshot.json"
if ([string]::IsNullOrWhiteSpace($SnapshotPath)) {
    if (Test-Path -LiteralPath $defaultSnapshotPath) {
        $SnapshotPath = $defaultSnapshotPath
    }
} else {
    if (-not (Test-Path -LiteralPath $SnapshotPath -PathType Leaf)) {
        throw "No encontré el snapshot indicado: $SnapshotPath"
    }
    $SnapshotPath = (Resolve-Path -LiteralPath $SnapshotPath).Path
}
if (-not [string]::IsNullOrWhiteSpace($SnapshotPath)) {
    $env:PLAYGROUND_SNAPSHOT_PATH = $SnapshotPath
}
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

$apiProbe = "http://127.0.0.1:$ApiPort/api/v1/playground/fixtures"
try {
    $apiReady = $false
    $apiProbeError = "sin respuesta"
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if ($apiProcess.HasExited) {
            $apiProbeError = "el proceso API terminó antes de responder"
            break
        }
        try {
            $probe = Invoke-WebRequest -Uri $apiProbe -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($probe.StatusCode -eq 200 -and $probe.Content -match '"fixtures"') {
                $apiReady = $true
                break
            }
            $apiProbeError = "respondió HTTP $($probe.StatusCode) sin el contrato de fixtures"
        } catch {
            $apiProbeError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $apiReady) {
        throw "El API del playground no respondió 200 en $apiProbe. Puede haber otro proceso ocupando el puerto $ApiPort. Detalle: $apiProbeError"
    }

    Write-Host "Playground API: http://127.0.0.1:$ApiPort"
    Write-Host "Playground web: http://localhost:$WebPort/playground"
    if ([string]::IsNullOrWhiteSpace($env:PLAYGROUND_SNAPSHOT_PATH)) {
        Write-Host "Data source: demo fixture"
    } else {
        Write-Host "Data source: real snapshot [$env:PLAYGROUND_SNAPSHOT_PATH]"
    }
    Write-Host "Fake mode: disponible sin credenciales. Real mode: requiere AGENT_MANAGED_ENDPOINT y AGENT_MANAGED_API_KEY."
    Write-Host "No se inicia Postgres, Redis, workers, scheduler, release ni harness."

    Push-Location (Join-Path $repoRoot "apps\web")
    try {
        & $next dev --port $WebPort
    } finally {
        Pop-Location
    }
}
finally {
    if (-not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id
    }
}
