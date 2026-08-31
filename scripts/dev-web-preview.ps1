[CmdletBinding()]
param(
  [int]$Port = 3000,
  [switch]$Build,
  [string]$RadarId = "preview-palermo",
  [switch]$WithProposal,
  [switch]$NoMocks,
  [switch]$Open
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot

Write-Host "`n[preview] Umbral web preview - sin backend/db`n" -ForegroundColor Cyan

if ($NoMocks) {
  Write-Host "  Mocks: OFF (parity con Railway prod - requiere backend corriendo)" -ForegroundColor Yellow
  $env:NEXT_PUBLIC_USE_MOCKS = "0"
  $env:USE_MOCKS = "0"
  Remove-Item Env:NEXT_PUBLIC_MOCK_CHAT_PROPOSAL -ErrorAction SilentlyContinue
} else {
  Write-Host "  NEXT_PUBLIC_USE_MOCKS=1 + UMBRAL_ACCESS_MODE=product_session" -ForegroundColor DarkGray
  $env:NEXT_PUBLIC_USE_MOCKS = "1"
  $env:USE_MOCKS = "1"
  if ($WithProposal) {
    Write-Host "  NEXT_PUBLIC_MOCK_CHAT_PROPOSAL=1 (sticky propuesta 1a visible)" -ForegroundColor Green
    $env:NEXT_PUBLIC_MOCK_CHAT_PROPOSAL = "1"
  } else {
    Remove-Item Env:NEXT_PUBLIC_MOCK_CHAT_PROPOSAL -ErrorAction SilentlyContinue
  }
}
$env:UMBRAL_ACCESS_MODE = "product_session"
$env:UMBRAL_E2E_BYPASS_ACCESS = "1"
$env:SESSION_COOKIE_NAME = "umbral_local_session"

if ($NoMocks -and -not $Build) {
  Write-Host "  Radar mock: $RadarId - Chat real contra /api (necesita API corriendo)" -ForegroundColor DarkGray
} else {
  Write-Host "  Radar mock: $RadarId (tambien: preview-belgrano, preview-almagro)" -ForegroundColor DarkGray
}
Write-Host ""

# URL helpers
$baseUrl = "http://localhost:$Port/radar/$RadarId"
$proposalUrl = "$baseUrl`?chat_preview=proposal"

function Test-PortAvailable {
  param([int]$P)
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $P)
    $listener.Start()
    $listener.Stop()
    return $true
  } catch { return $false }
}

if (-not (Test-PortAvailable -P $Port)) {
  Write-Host "[preview] Puerto $Port ocupado. Probá -Port 3001`n" -ForegroundColor Red
}

if ($Build) {
  Write-Host "[preview] Build prod + start (parity Railway)..." -ForegroundColor Yellow
  if ($NoMocks) {
    Write-Host "  Sin mocks: hace next build real. Si no tenés backend, el chat fallará (esperado)." -ForegroundColor DarkGray
  }
  npm --workspace @umbral/web run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
  $env:PORT = "$Port"
  Write-Host "`n[preview] Abri:" -ForegroundColor Green
  Write-Host "  Normal:               $baseUrl" -ForegroundColor White
  Write-Host "  Sticky propuesta 1a:  $proposalUrl  (nuevo - barra fija arriba del composer)" -ForegroundColor White
  Write-Host "  Lista radares:        http://localhost:$Port/radar" -ForegroundColor White
  Write-Host "  Playground real:      http://localhost:$Port/playground`n" -ForegroundColor White
  Write-Host "  Para salir: Ctrl+C`n" -ForegroundColor DarkGray
  if ($Open) { Start-Process $proposalUrl }
  npx --workspace @umbral/web next start --port $Port
} else {
  Write-Host "[preview] Dev server (HMR)...`n" -ForegroundColor Yellow
  Write-Host "  URLs:" -ForegroundColor Green
  Write-Host "    Shell:                 $baseUrl" -ForegroundColor White
  Write-Host "    Sticky propuesta 1a:   $proposalUrl  <- probá este para ver el fix 1a" -ForegroundColor Cyan
  Write-Host "    Lista radares:         http://localhost:$Port/radar" -ForegroundColor White
  Write-Host "    Playground real:       http://localhost:$Port/playground`n" -ForegroundColor White
  Write-Host "  Flags:" -ForegroundColor DarkGray
  Write-Host "    -WithProposal  fuerza propuesta sticky sin ?query (env var)" -ForegroundColor DarkGray
  Write-Host "    -NoMocks       sin mocks, contra API real (necesita .env.local + docker up)" -ForegroundColor DarkGray
  Write-Host "    -Build         build prod parity Railway (next build + next start)" -ForegroundColor DarkGray
  Write-Host "    -Port 3001     cambia puerto si 3000 ocupado`n" -ForegroundColor DarkGray
  Write-Host "  Tip: hover card -> pin, Esc cierra sheet, Enter envía, Shift+Enter nueva línea." -ForegroundColor DarkGray
  Write-Host "  Para salir: Ctrl+C`n" -ForegroundColor DarkGray
  if ($Open) { Start-Process $proposalUrl }
  Set-Location "$repoRoot/apps/web"
  npx next dev --port $Port
}

Pop-Location
