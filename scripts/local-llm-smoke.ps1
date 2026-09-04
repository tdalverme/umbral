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
import json
from umbral.agent.intent.v5 import InterpretationCompilerV5
from umbral.application.conversation.v5.contracts import TurnContextV5
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from pathlib import Path

# Cargar el snapshot de conceptos que consume el intérprete V5.
seed = load_concepts_seed()
concept_catalog = tuple(
    {
        "key": concept.key,
        "description": concept.name,
        "matcher_type": concept.matcher_type,
        "computable": bool(concept.compute_policy.get("computable", True)),
        "aliases": list(concept.aliases),
    }
    for concept in seed.concepts
)
schema = json.loads(Path("contracts/agent/v5/interpretation-schema-v5.json").read_text(encoding="utf-8"))

import os
gw = ManagedModelGateway(endpoint=os.environ["AGENT_MANAGED_ENDPOINT"], api_key=os.environ["AGENT_MANAGED_API_KEY"], model=os.environ["AGENT_MODEL_NAME"], timeout_seconds=30)
interpreter = InterpretationCompilerV5(
    gateway=gw,
    schema=schema,
    prompt_version="test-local",
    model_version=os.environ["AGENT_MODEL_NAME"],
    concept_catalog=concept_catalog,
)
context = TurnContextV5(
    user_id="smoke-user", session_id="smoke-session", active_radar_ref="radar:smoke",
    active_radar_version=1, current_filters=(), active_desires=(), pending_action=None,
    focused_entity=None, verified_listing_refs=(),
    allowed_capabilities=("express_desire", "set_filter", "query", "unsupported_request"),
    untrusted_content=(), context_schema_version="5", correlation_id="smoke-correlation",
)
res = interpreter.interpret(message_text="$Phrase", context=context)
print("---RESULTADO---")
for act in res.acts:
    print(f"kind={act.kind} evidence={[span.text for span in act.evidence_spans]}")
    if hasattr(act, "concept_links"):
        print("concept_refs=", [link.concept_ref for link in act.concept_links])
"@

# Escapar comillas para PowerShell
$scriptPath = Join-Path $env:TEMP "umbral-llm-smoke.py"
Set-Content -LiteralPath $scriptPath -Value $script -Encoding utf8
& .venv\Scripts\python.exe $scriptPath
$code = $LASTEXITCODE
Remove-Item $scriptPath -ErrorAction SilentlyContinue
Pop-Location
exit $code
