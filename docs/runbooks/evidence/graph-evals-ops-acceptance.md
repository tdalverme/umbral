# Evidence: graph-evals-ops acceptance (H4.4)

**Feature**: 012-graph-evals-ops | **Date**: 2026-08-10 | **Branch**: `main`

Cierre del incremento `graph-evals-ops` (Épica H4.4, UM-H4-026 a UM-H4-030 +
ADR de proveedor de modelo), que cierra el hito `conversational-radar`
(UM-H4-001 a UM-H4-030). Spec: `specs/012-graph-evals-ops/spec.md`; plan:
`specs/012-graph-evals-ops/plan.md`; tareas: `specs/012-graph-evals-ops/tasks.md`.

## Resumen del incremento

- **Dataset golden de conversaciones** (UM-H4-026): `contracts/agent-evals/v1/
  conversations-golden-v1.json` (+ schema) con 21 casos curados (7 familias x
  3, revisado por producto, 0 PII) y parser puro
  `application/agent_evals/golden.py` (FR-001..FR-004, Q5).
- **Evals del graph** (UM-H4-027): runner sobre el stack v3 REAL con gateway
  determinista scriptado (Q4), métricas por caso derivadas de los runs
  persistidos (`metrics.py`), gate de regresiones estricto en señales
  deterministas con umbrales para costo/latencia (`regression.py`,
  `agent_evals.regression_blocked`), persistencia en `agent_eval_suites`/
  `agent_eval_case_results` (migración `0012_agent_evals`) (FR-005..FR-008).
- **Releases versionadas y revertibles** (UM-H4-028): registry append-only
  `contracts/agent-evals/v1/graph-releases-v1.json` (componentes versionados,
  `affected_case_ids`, activación híbrida Q6 con `approved_by` +
  `approval_evidence` para prompts/modelos) y stamp de `release_id` en
  `agent_graph_runs` (0 mutación de runs previos) (FR-009..FR-011).
- **Presupuestos y rate limits** (UM-H4-029): `application/agent/budgets.py`
  (política pura + consumo derivado de runs x tabla de precios), gate pre-run
  en `ChatRuntime` con bloqueo duro recuperable (Q3), advertencia vía evento
  `chat.budget_warning`, rechazo tipado de concurrencia; eventos
  `agent.budget_*`/`agent.rate_limit_exceeded` (FR-012..FR-016).
- **Dashboard del agente** (UM-H4-030, P1): `application/agent_ops/` +
  repo de agregación sobre runs/evals, `api/routers/agent_ops.py` de solo
  lectura (acción `ops.agent.read`), página web `(protected)/ops/agent`
  (FR-017..FR-019).
- **ADR de proveedor de modelo** (diferido H4.1/H4.2/H4.3 asignado a H4.4,
  Q1): `docs/decision-records/0001-model-provider.md` (5 criterios con
  evidencia de evals, decisión, riesgos, monitoreo) + conformance test
  (FR-022).
- **Harness**: `scripts/check-evals.ps1` registrado en `check.ps1`
  (gate en adapter simulado, Q4) y flujo real opt-in
  `scripts/run-real-evals.ps1` fuera de CI con presupuesto de eval acotado
  (FR-020/FR-021).

## Verificación

| Escenario quickstart | Resultado |
| --- | --- |
| 1. Dataset golden y conformance (7 familias x >=3, 0 PII, schema) | PASS |
| 2. Eval del graph con adapter simulado (21 casos, metricas, reproducible) | PASS |
| 3. Gate de regresiones: bloquea y deja pasar (release declarada, thresholds) | PASS |
| 4. Presupuestos y rate limits (warning, bloqueo duro recuperable, concurrencia, aislamiento) | PASS |
| 5. Dashboard del agente (agregados = registros fuente, regresiones vinculadas, 0 PII) | PASS |
| 6. ADR de proveedor de modelo (estructura y versionado) | PASS |
| 7. Harness `check-evals.ps1` + migración 0012 up/down + inventario cerrado | PASS (85 tests) |

Comandos:

```powershell
$env:PYTHONPATH = "src"
uv run pytest tests/contract/test_agent_evals_golden.py tests/contract/test_agent_evals_releases.py tests/contract/test_agent_evals_price.py tests/contract/test_agent_evals_regression.py tests/contract/test_model_provider_adr.py tests/unit/application/agent_evals tests/unit/application/agent/test_budgets.py tests/unit/application/agent_ops tests/unit/config/test_agent_settings.py tests/integration/agent_evals tests/integration/agent_ops/test_overview.py tests/migrations/test_0012_agent_evals.py tests/architecture/test_agent_evals_boundaries.py -q
.\scripts\check-evals.ps1            # incluye integración (requiere Docker)
.\scripts\check-migrations.ps1       # offline upgrade/downgrade + inventario cerrado
npm --workspace @umbral/web run api:generate
npm --workspace @umbral/web run api:check   # drift solo por cliente regenerado sin commitear
```

La migración `0012_agent_evals` se validó en
`tests/migrations/test_0012_agent_evals.py` (determinista, sin Docker), se
aplica al head en las integraciones, y el inventario cerrado de
`check-migrations.ps1` incluye `agent_eval_suites`,
`agent_eval_case_results` y `search_profile_update_proposals`.

## Decisiones de clarificación aplicadas (sesiones 2026-08-10)

1. Q1: el ADR de proveedor de modelo se incluye como entregable (diferido
   asignado a H4.4 en tres notas de aceptación) y queda vinculado al harness.
2. Q2: gate estricto en señales deterministas (0 tolerancia) con umbrales de
   política para costo/latencia (convención H3.4).
3. Q3: presupuesto agotado = bloqueo duro recuperable (ventana o acción
   explícita, 0 degradación de modelo).
4. Q4: evals híbridos — el gate corre con adapter determinista simulado; el
   proveedor real en flujo separado, programado y con presupuesto de eval
   acotado.
5. Q5: dataset golden con >=3 casos por familia (21 total), versionado y
   ampliable.
6. Q6: activación de releases híbrida — automática para código/topología/
   schemas; aprobación explícita de operador para prompts/modelos.

## Diferidos a seguimiento

- Gate completo `.\scripts\check.ps1` desde checkout limpio en CI (los suites
  con Docker dependen del engine local; `api:check` exige el cliente web
  regenerado commiteado, convención del repo).
- Fallos pre-existentes ajenos a este incremento, dependientes del entorno:
  `test_rq_worker_uses_umbral_queue_and_json_serializer` (Redis local),
  `test_supabase_adapter.py` (endpoint) y el `PermissionError` de
  pytest-asyncio sobre el temp dir (`pytest-of-Usuario`) que afecta a los
  tests async de `test_openapi_versioning.py`.
- El wiring de producción del runtime de chat y del servicio de dashboard en
  `api/dependencies.py` (dejados en `None`) queda como seguimiento operativo
  de H4/H6; el harness eval compone su propio stack (R-03/R-12).
