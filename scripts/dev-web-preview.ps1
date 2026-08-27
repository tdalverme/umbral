[CmdletBinding()]
param(
  [int]$Port = 3000,
  [switch]$Build,
  [string]$RadarId = "preview-palermo"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot

Write-Host "`n[preview] Umbral web preview — sin backend/db`n" -ForegroundColor Cyan
Write-Host "  NEXT_PUBLIC_USE_MOCKS=1" -ForegroundColor DarkGray
Write-Host "  Radar mock: $RadarId (también: preview-belgrano, preview-almagro)`n" -ForegroundColor DarkGray

$env:NEXT_PUBLIC_USE_MOCKS = "1"
$env:SESSION_COOKIE_NAME = "umbral_local_session"

if ($Build) {
  Write-Host "[preview] Build prod + start..." -ForegroundColor Yellow
  npm --workspace @umbral/web run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
  $env:PORT = "$Port"
  Write-Host "`n[preview] Abrí http://localhost:$Port/radar/$RadarId`n" -ForegroundColor Green
  Write-Host "  Lista mock: 8 curadas (6 con geo + 2 sin) · Pins terracota selected · espiral colisión 1+5" -ForegroundColor DarkGray
  Write-Host "  Sidebar: 3 radares mock · Chat: placeholder bienvenida + chips`n" -ForegroundColor DarkGray
  npx --workspace @umbral/web next start --port $Port
} else {
  Write-Host "[preview] Dev server (HMR)..." -ForegroundColor Yellow
  Write-Host "`n  URLs:" -ForegroundColor Green
  Write-Host "    Shell:            http://localhost:$Port/radar/$RadarId" -ForegroundColor White
  Write-Host "    Lista radares:    http://localhost:$Port/radar" -ForegroundColor White
  Write-Host "    Playground real:  http://localhost:$Port/playground`n" -ForegroundColor White
  Write-Host "  Tip: probá ?listingId=listing-1 para deeplink, hover card → pin, Esc para cerrar sheet." -ForegroundColor DarkGray
  Write-Host "  Para salir: Ctrl+C`n" -ForegroundColor DarkGray
  # Usa el script del package root que ya proxy a web
  npm run dev --workspace @umbral/web -- --port $Port
}

Pop-Location
