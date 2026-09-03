[CmdletBinding()]
param(
  [string]$Phrase = "Prefiero deptos con poco ruido",
  [switch]$UsePreviewVars
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Push-Location $repoRoot

# 1) Cargar .env.local si existe
if (Test-Path ".env.local") {
  Get-Content ".env.local" | ForEach-Object {
    if ($_ -match "^\s*([^#=]+?)\s*=\s*(.*)\s*$") {
      $k = $matches[1].Trim(); $v = $matches[2].Trim()
      if (-not [string]::IsNullOrWhiteSpace($k)) { Set-Item -Path "env:$k" -Value $v }
    }
  }
}

# 2) Si pide -UsePreviewVars intenta traerlas de Railway (requiere `railway login` y `RAILWAY_TOKEN`)
if ($UsePreviewVars) {
  Write-Host "[llm-smoke] Trayendo AGENT_* de Railway preview..." -ForegroundColor Cyan
  $varsJson = & npx @railway/cli@5.27.2 variables --service api -e preview --json 2>$null | Out-String
  if ($LASTEXITCODE -eq 0 -and $varsJson) {
    $vars = $varsJson | ConvertFrom-Json
    foreach ($key in @("AGENT_MANAGED_ENDPOINT","AGENT_MANAGED_API_KEY","AGENT_MODEL_NAME","AGENT_MODEL_PROVIDER")) {
      $val = $vars.$key
      if ($val) { Set-Item -Path "env:$key" -Value $val; Write-Host "  $key=***" -ForegroundColor DarkGray }
    }
  } else {
    Write-Host "[llm-smoke] No se pudo leer Railway vars. Copialas a mano a .env.local desde Railway → api → Variables: AGENT_MANAGED_ENDPOINT, AGENT_MANAGED_API_KEY, AGENT_MODEL_NAME" -ForegroundColor Yellow
  }
}

$endpoint = $env:AGENT_MANAGED_ENDPOINT
$apiKey = $env:AGENT_MANAGED_API_KEY
$model = $env:AGENT_MODEL_NAME
if (-not $endpoint -or -not $apiKey) {
  Write-Host "`n[llm-smoke] Falta AGENT_MANAGED_ENDPOINT / AGENT_MANAGED_API_KEY en env." -ForegroundColor Red
  Write-Host "Opción A: ponlos en .env.local (copialos de Railway preview → api → Variables)" -ForegroundColor Yellow
  Write-Host "Opción B: corre con -UsePreviewVars si tenés 'railway login' hecho`n" -ForegroundColor Yellow
  Pop-Location; exit 1
}
if (-not $model) { $env:AGENT_MODEL_NAME = "gpt-4.1-mini"; $model = "gpt-4.1-mini" }

Write-Host "`n[llm-smoke] Probando LLM real: model=$model endpoint=$endpoint" -ForegroundColor Cyan
Write-Host "  Frase: `"$Phrase`"`n" -ForegroundColor White

$env:PYTHONPATH = "src"
$script = @"
import json, pathlib
from umbral.application.agent.tools.preference_interpreter import ConceptOption, resolve_concept
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from pathlib import Path

# Cargar conceptos + vocabulario como hace production.py
seed = json.loads(Path("contracts/criteria/v1/concepts-seed-v1.json").read_text(encoding="utf-8"))
from umbral.infrastructure.agent.tools.preferences_loader import load_preference_vocabulary
vocab = load_preference_vocabulary()
vocab_map = {}
for e in vocab.entries:
    vocab_map.setdefault(e.intent.concept_key, []).extend(list(e.aliases))

concepts = tuple(
    ConceptOption(
        key=str(c["key"]),
        description=str(c.get("name") or c["key"]),
        matchers=(str(c["matcher_type"]),),
        aliases=tuple(vocab_map.get(str(c["key"]), ())[:6]),
    )
    for c in seed.get("concepts", [])
)

import os
gw = ManagedModelGateway(endpoint=os.environ["AGENT_MANAGED_ENDPOINT"], api_key=os.environ["AGENT_MANAGED_API_KEY"], model=os.environ["AGENT_MODEL_NAME"], timeout_seconds=30)
res = resolve_concept(phrase="$Phrase", concepts=concepts, gateway=gw, prompt_version="test-local", model_version=os.environ["AGENT_MODEL_NAME"])
print("---RESULTADO---")
print(f"kind={getattr(res,'kind',None)} concept_key={getattr(res,'concept_key',None)} polarity={getattr(res,'polarity',None)} confidence={getattr(res,'confidence',None)} reason={getattr(res,'reason','')[:120]}")
if res and res.kind=="structured":
    print("✓ MAPEO OK ->", res.concept_key)
else:
    print("✗ NO MAPEO - revisa catalog/alias")
"@

# Escapar comillas para PowerShell
$scriptPath = Join-Path $env:TEMP "umbral-llm-smoke.py"
Set-Content -LiteralPath $scriptPath -Value $script -Encoding utf8
& .venv\Scripts\python.exe $scriptPath
$code = $LASTEXITCODE
Remove-Item $scriptPath -ErrorAction SilentlyContinue
Pop-Location
exit $code
