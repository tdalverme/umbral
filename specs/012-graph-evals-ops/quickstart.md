# Quickstart: Evals, costos y operacion del agente (H4.4)

Guia de validacion de extremo a extremo del incremento. Detalles de
implementacion en `tasks.md`; shapes y reglas en [data-model.md](./data-model.md)
y [contracts](./contracts/agent-evals-contracts-v1.md).

## Prerrequisitos

- Entorno local: `.venv\Scripts\Activate.ps1`, Postgres local o Docker
  (testcontainers para integracion).
- El stack v3 del graph (H4.3) existente; el harness usa el adapter
  determinista simulado (Q4: 0 costo, 0 proveedor real en CI).

## Escenario 1 — Dataset golden y conformance

**Comando**:

```powershell
uv run pytest tests/contract/test_agent_evals_golden.py tests/contract/test_agent_evals_releases.py tests/contract/test_agent_evals_price.py -q
```

**Resultado esperado**: PASS. El dataset parsea con cobertura de las 7
familias (>=3 casos por familia, Q5), 0 PII; las releases referencian casos
existentes; la tabla de precios cubre los model_version de las releases
(SC-001, FR-001..FR-004).

## Escenario 2 — Eval del graph con adapter simulado

**Comando**:

```powershell
uv run pytest tests/unit/application/agent_evals tests/integration/agent_evals -q
```

**Resultado esperado**: PASS. Cada caso del dataset corre sobre el stack v3
real con gateway determinista scriptado (R-03); las metricas por caso
(seleccion de tool, argumentos, grounding, confirmacion, outcome, costo)
se derivan de los runs registrados (R-04/R-05) y dos corridas del mismo
suite producen el mismo reporte (FR-007, SC-002).

## Escenario 3 — Gate de regresiones: bloquea y deja pasar

**Comando**:

```powershell
uv run pytest tests/unit/application/agent_evals/test_regression.py tests/contract/test_agent_evals_regression.py -q
```

**Resultado esperado**: PASS. Con baseline == candidato el gate pasa; una
candidata con cambio de comportamiento (respuestas scriptadas distintas)
sin release declarada bloquea (`agent_evals.regression_blocked`); la misma
candidata con `affected_case_ids` exactos y activacion valida (aprobacion de
operador si toca prompts/modelos, Q6) pasa; costo/latencia usan umbrales de
politica (FR-008, SC-002/SC-003).

## Escenario 4 — Presupuestos y rate limits

**Comando**:

```powershell
uv run pytest tests/integration/agent_evals/test_agent_budgets.py tests/unit/application/agent/test_budgets.py -q
```

**Resultado esperado**: PASS. Dentro del presupuesto el chat opera normal;
cerca del limite llega `agent.budget_warning` (sin interrumpir el turno);
al agotarse se aplica bloqueo duro recuperable (`agent.budget_exhausted`,
ventana o accion explicita, 0 degradacion de modelo, Q3); la concurrencia
por usuario se rechaza con estado tipado; los excesos quedan auditados en
eventos sin PII (FR-012..FR-016, SC-004).

## Escenario 5 — Dashboard del agente (P1)

**Comando** (con stack local y runs de chat previos):

```powershell
uv run pytest tests/integration/agent_ops tests/unit/application/agent_ops -q
# y en la web: abrir /ops/agent con permiso product.agent_ops.read
```

**Resultado esperado**: PASS. Las cifras del dashboard (latencia p95,
errores, tool success, interrupts, tokens, costo, regresiones de eval con
su release y gate) coinciden con los registros fuente; `data_as_of` visible;
0 PII y 0 acciones de mutacion (FR-017..FR-019, SC-005).

## Escenario 6 — ADR de proveedor de modelo

**Comando**:

```powershell
uv run pytest tests/contract/test_model_provider_adr.py -q
```

**Resultado esperado**: PASS. `docs/decision-records/0001-model-provider.md`
existe, versionado, compara alternativas con los 5 criterios (costo,
calidad, latencia, privacidad, operabilidad) con evidencia de los evals del
dataset golden, y documenta decision, riesgos y monitoreo (FR-022, SC-006).

## Escenario 7 — Harness completo

**Comando**:

```powershell
.\scripts\check-evals.ps1
.\scripts\check.ps1
```

**Resultado esperado**: PASS. `check-evals.ps1` corre contratos, unit,
integracion (Postgres via testcontainers), migracion 0012 y arquitectura
con el gate en adapter simulado; `check.ps1` registra el nuevo harness por
surface detection sin regresiones en las suites previas de H4 (FR-020,
FR-021, SC-007). El flujo con proveedor real queda en
`scripts/run-real-evals.ps1` (opt-in, presupuesto de eval acotado, fuera de
CI; Q4).

## Notas de verificacion

- El gate nunca depende de un mock de superficie: la suite corre sobre el
  stack v3 real con gateway determinista (R-03) y las metricas derivan de
  registros persistidos (R-04).
- La migracion 0012 se verifica up/down y el inventario cerrado de
  `check-migrations.ps1` se actualiza con `agent_eval_suites`,
  `agent_eval_case_results` y `agent_graph_runs.release_id`.
- 0 PII en dataset, reportes, eventos y dashboard; la evidencia del
  incremento se consolida en `docs/runbooks/evidence/graph-evals-ops-acceptance.md`.
