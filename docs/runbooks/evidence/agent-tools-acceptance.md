# Evidence: agent-tools acceptance (H4.2)

**Feature**: 010-agent-tools | **Date**: 2026-08-09 | **Branch**: `main`

Cierre local del incremento `agent-tools` (Épica H4.2, UM-H4-007 a
UM-H4-016). Spec: `specs/010-agent-tools/spec.md`; plan:
`specs/010-agent-tools/plan.md`; tareas: `specs/010-agent-tools/tasks.md`
(49/49 completadas).

## Resumen del incremento

- **Contrato de tools versionado**: `contracts/agent/tools/tool-contract-v1.json`
  declara las 8 tools con la política común (identidad, search scope, schema,
  timeout, idempotencia, confirmación, redacción). Schemas de agente v2
  (`state-schema-v2`, `graph-topology-v2`, `reply-schema-v2`) con el loop de
  tools acotado (`AGENT_TOOLS_MAX_CALLS_PER_TURN` = 5).
- **Registry + executor común** (`src/umbral/agent/tools/`): valida identidad/
  scope/schema/confirmación/idempotencia/timeout, redacta salidas
  (forbidden_keys del events registry + `AGENT_TOOLS_OUTPUT_MAX_ITEMS`) y
  registra cada invocación como `agent_node_runs` con `node_kind='tool'`.
- **Propuestas de perfil durables** (clarificaciones Q1/Q2/Q4/Q5): tabla
  `search_profile_update_proposals` (migración `0010_agent_tools`) con
  `base_profile_version`, estado determinista (pending → approved vía apply;
  rejected por obsolescencia/vencimiento), idempotency key de un solo uso y
  replay recuperable; obsolescencia = `ConcurrencyConflict` del radar.
- **8 tools delgadas** sobre servicios existentes (radar/scoring/feedback/
  criteria): `get_search_profile`, `find_matches` (solo lectura, estado
  explícito sin run/stale), `explain_match`, `compare_listings`,
  `record_feedback` (like/dislike con razones, propuesta de aprendizaje),
  `search_urban_context` (P1, seam `list_urban_signals` con precisión).
- **Eventos**: `search_profile.update_proposed.v1` /
  `search_profile.update_applied.v1` (DoD #4).
- **Suite de abuso determinista** (UM-H4-016) como gate: acceso cruzado en
  las 8 tools, args manipulados, prompt injection, outputs excesivos y
  mutación sin confirmación — 0 LLM.
- **Harness** `scripts/check-agent-tools.ps1` registrado en `check.ps1`;
  `infrastructure/agent/composition.py` para tests/harness; settings
  `AGENT_TOOLS_*` + `AGENT_PROPOSAL_TTL_HOURS`; duty de vencimiento
  `expire_search_profile_proposals` en el scheduler.

## Verificación

| Escenario quickstart | Resultado |
| --- | --- |
| 1. Conformance: tool contract y schemas v2 | PASS |
| 2. Ciclo de vida de propuestas (propose→confirm→apply, replay, obsolescencia, vencimiento) | PASS |
| 3. Tools de lectura (perfil, matches, explicación, comparación) | PASS |
| 4. Feedback desde el chat | PASS |
| 5. Contexto urbano (P1) | PASS |
| 6. Suite de abuso (gate UM-H4-016) | PASS |
| 7. Arquitectura y harness | PASS |

Comandos:

```powershell
$env:PYTHONPATH = "src"
.\scripts\check-agent-tools.ps1        # PASS: 93 tests (unit + contract + migrations + integración con Postgres/testcontainers)
.\scripts\check.ps1                    # orquesta check-agent.ps1 y check-agent-tools.ps1
uv run ruff check .                    # limpio en las superficies tocadas
uv run mypy src tests                  # limpio en las superficies tocadas
```

La migración `0010_agent_tools` se validó up y down en los tests de
migración (`tests/migrations/test_0010_agent_tools.py`) y se aplicó al head
en cada test de integración (alembic upgrade → head incluyó `0010`).

## Decisiones de clarificación aplicadas (sesión 2026-08-09)

1. Propuestas durables y auditables con ciclo de vida determinista (Q1/Q5).
2. Todo cambio de perfil requiere confirmación (propose → confirm → apply).
3. `find_matches` estrictamente de solo lectura.
4. Obsolescencia: la propuesta registra `base_profile_version`; si el perfil
   cambió, apply la rechaza con error tipado.
5. Rechazo solo por obsolescencia o vencimiento; el rechazo interactivo y la
   edición son H4.3.
6. El feedback del chat cubre solo like/dislike con razones opcionales.

## Diferidos a seguimiento (convención de incrementos previos)

- Gate completo desde checkout limpio en CI.
- ADR del proveedor de modelo y evals del graph (H4.4).
- `documentación runtime-local.md` si toca deployment (no se tocó).
