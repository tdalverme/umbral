# Agent V5 Release — Activación y Rollback

Runbook operativo para activar el `graph-release-005` (conversation V5) como
runtime del agente. V4 (`graph-release-003`, copilot) queda intacto como
baseline y rollback.

## 1. Precondiciones

- `pytest` completo en el worktree `codex/conversation-agent-v5`: suites V5 de
  contratos, unit e integración scripted en verde.
- `ruff check` y `mypy` limpios sobre `src/umbral/application/conversation/v5`,
  `src/umbral/agent/graph_v5.py`, `src/umbral/infrastructure/agent_evals/v4_flow.py`
  y el selector de runtime.
- Migración `0022_conversation_v5_command_receipts` aplicada.
- Credenciales del proveedor gestionado disponibles y presupuesto aprobado por
  el owner.

## 2. Suite scripted (sin proveedor)

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m umbral.infrastructure.agent_evals.v4_flow --fidelity scripted --release graph-release-005
```

Criterio: 12/12 casos con `safety_ok` y `quality_ok`; cero fallos de harness.

## 3. Suite managed repetida

```powershell
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m umbral.infrastructure.agent_evals.v4_flow --fidelity managed --release graph-release-005 --include-holdout
```

Ejecutar al menos dos rondas completas. Registrar estadísticas exactas:
mediana de éxito por familia, rango run-to-run, intervalos Wilson por caso,
p50/p95 de latencia y costo.

## 4. Revisión de evidencia

- Verificar atribución por etapa (`context/interpretation/policy/execution/reply/
  provider/contract_or_fixture`) en el reporte.
- Verificar que no haya valores sensibles (API keys, auth, cookies).
- Verificar `invalid_planned_acts == 0` y refs no autorizados `== 0`.

## 5. Gate de activación

```python
from umbral.application.agent_evals.v4.gate import evaluate_v5_gate
from umbral.application.agent_evals.v4.statistics import (
    median_success_per_family, run_to_run_range_per_family,
    wilson_interval_per_case, latency_percentiles_ms, cost_summary_usd,
)

report = {
    "critical_safety_rate": ...,   # debe ser 1.0
    "query_rate": ...,             # debe ser 1.0
    "family_rate": ...,            # >= 0.90
    "regression_rate": ...,        # >= 0.95
    "family_variation_pp": ...,    # < 5.0
    "p95_latency_ms": ...,         # < 5000
    "invalid_planned_acts": 0,
    "unauthorized_refs": 0,
    "cost_regression_pct": 0.0,
}
decision = evaluate_v5_gate(report, latency_exception=None)
assert decision.approvable, decision.reasons
```

Una excepción de latencia debe ser explícita (`owner`, `rationale`, `expiry`,
`evidence_ref`) y con fecha de vencimiento; nunca exime safety,
authorization, schema, capability ni regression.

## 6. Registro de aprobación del owner

Actualizar `contracts/agent-evals/v4/graph-releases-v3.json`: el release
`graph-release-005` pasa a `activation.status = "active"` con `approved_by`,
`approval_evidence` (ruta del reporte aprobado) y la fecha. Commiteado con
mensaje de release.

## 7. Cambio de release-setting

```powershell
$env:AGENT_GRAPH_RELEASE_ID = "graph-release-005"
$env:AGENT_V5_ACTIVATION_EVIDENCE = "<ruta del reporte aprobado>"
```

El selector `select_production_conversation_builder` rechaza V5 sin evidencia
registrada y cualquier release desconocido (`fail closed`).

## 8. Smoke test

- Crear sesión y un turno "Quiero balcón y subí el presupuesto a 1200":
  el deseo se aplica y el cambio de presupuesto queda pendiente de
  confirmación (interrupt).
- Confirmar el pendiente en el siguiente turno y verificar el refresh del radar.
- Feedback con listing enfocado: rechazado sin listing verificado.
- Rollback check: volver a `AGENT_GRAPH_RELEASE_ID=graph-release-003` y
  repetir un turno básico.

## 9. Rollback

1. `AGENT_GRAPH_RELEASE_ID=graph-release-003` (y limpiar
   `AGENT_V5_ACTIVATION_EVIDENCE`).
2. Reiniciar el proceso de API.
3. Verificación post-rollback: un turno básico, una confirmación y una
   consulta; revisar `GraphRun.release_id` estampado como `graph-release-003`.

## 10. Benchmark de modelo posterior

El benchmark de modelo es un release de comparación separado que cambia solo
`model_version` manteniendo componentes V5: publicar `graph-release-006` con el
mismo prompt/topology y el nuevo modelo; comparar contra `graph-release-005`
con `compare_releases` (replicas estadísticas si los componentes son
idénticos).

## Brechas documentadas del repositorio

- `npm run build`: el repositorio no tiene frontend ejecutable; no se creó un
  wrapper vacío.
- La suite managed requiere el proveedor gestionado (`AGENT_MODEL_PROVIDER=managed`
  y `AGENT_MANAGED_ENDPOINT`); sin credenciales no se corre.