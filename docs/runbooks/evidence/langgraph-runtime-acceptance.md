# Evidencia de cierre: Runtime LangGraph (H4.1)

**Incremento**: `009-langgraph-runtime` | **Fecha**: 2026-08-09

## Alcance

UM-H4-001 a UM-H4-006 (Epica H4.1 - Runtime LangGraph), según el spec
`specs/009-langgraph-runtime/spec.md` con las clarificaciones 2026-08-09
(retención: sesiones/mensajes con la cuenta y checkpoints con ventana corta
default 30 días; segunda solicitud rechazada con "ejecución en curso"; estado
de sesión espejo del search profile; solo respuestas completas persistidas).

## Resultado por SC

- **SC-001 (sesiones/mensajes persistentes)**: PASS. `chat_sessions` +
  `chat_messages` con inmutabilidad (0 UPDATE), historial en orden, límite
  `CHAT_MESSAGE_MAX_LENGTH`, estado espejo del profile y eventos
  `chat.session_created.v1`/`chat.message_created.v1`. Unit en
  `tests/unit/application/chat/test_service.py`, integración en
  `tests/integration/chat/test_session_repo.py` (testcontainers), conformance en
  `tests/contract/test_agent_chat_events.py`.
- **SC-002 (estado versionado y serializable)**: PASS. `contracts/agent/v1/
  state-schema-v1.json` con `schema_version` registrado en cada checkpoint;
  round-trip JSON-safe (FR-005). Conformance en
  `tests/contract/test_agent_state_schema.py` y unit en
  `tests/unit/agent/test_state.py`.
- **SC-003 (aislamiento y retención)**: PASS. Checkpointer Postgres con
  `setup()`, strict msgpack (`AGENT_STRICT_MSGPACK`), threads aislados por
  thread id y `delete_thread`; el acceso cruzado se deniega en el servicio antes
  de tocar el checkpointer; `purge_agent_checkpoints` borra solo threads
  inactivos fuera de la ventana y nunca toca el historial, registrada como duty
  del scheduler. Integración en `tests/integration/agent/test_checkpointer.py` y
  `test_runtime_isolation.py`, unit en `tests/unit/infrastructure/agent/
  test_purge.py`.
- **SC-004 (gateway con salidas estructuradas)**: PASS. Puente `ModelGateway`
  con `FakeModelGateway` (default) y `ManagedModelGateway` (HTTP, timeout,
  reintento acotado `AGENT_MODEL_MAX_RETRIES`, validación contra
  `reply-schema-v1`, usage y versiones por llamada). Unit en
  `tests/unit/infrastructure/agent/test_managed_gateway.py` y
  `tests/unit/application/agent/test_model_gateway.py`.
- **SC-005 (reanudación sin duplicados)**: PASS. `ChatRuntime` con topología v1
  (`start → generate_reply → persist_reply`), ledger `effects_applied` en el
  estado, índice único parcial `uq_agent_graph_runs_session_active` (0 runs
  paralelos por sesión, incluye `interrupted`), rechazo tipado
  `ChatExecutionInProgress`, resume con `attempt+1` y 0 mensajes parciales.
  E2E en `tests/integration/agent/test_runtime_e2e.py`, unit en
  `tests/unit/agent/test_graph.py`.
- **SC-006 (runs auditables)**: PASS. `agent_graph_runs`/`agent_node_runs`/
  `agent_model_calls` con versiones, estados, latencia, errores, uso y
  correlación, 0 PII. Unit en `tests/unit/application/agent/test_run_recorder.py`.
- **SC-007 (harness, 0 superficies nuevas)**: PASS. `scripts/check-agent.ps1`
  registrado en `check.ps1` con el guard `agentSurface`; 0 endpoints HTTP de
  chat, 0 tools, 0 UI. Conformance en `tests/contract/test_agent_harness.py` y
  límites en `tests/architecture/test_agent_boundaries.py`.

## Recorrido de quickstart

Escenarios 1, 5, 6 y 7 (conformance, gateway, purga, arquitectura) pasan en
local; los escenarios 2, 3 y 4 requieren Docker/testcontainers y se verifican en
CI según la convención de los incrementos previos. Resultado detallado en
`specs/009-langgraph-runtime/quickstart.md`.

## Detalles de implementación

- Capa `agent` (`src/umbral/agent/`): `state.py` (schema v1 JSON-safe),
  `events.py` (eventos tipados), `graph.py` (topología v1 sobre LangGraph,
  efectos por ledger), `runtime.py` (claim/reanudación/streaming/rechazo).
- Aplicación: `application/chat` (contratos/puertos/service con eventos de
  producto) y `application/agent` (runs + `ModelGateway` + recorder).
- Infraestructura: `infrastructure/agent/` (checkpointer Postgres con strict
  msgpack, purge, gateways fake/managed), modelos/repos de chat y agent,
  migración `0009_langgraph_runtime` (5 tablas, 6 ENUMs, índice único parcial).
- Contratos: `contracts/agent/v1/{state-schema,graph-topology,reply-schema}-v1.json`;
  events registry ampliado con `chat.session_created.v1` y
  `chat.message_created.v1` (contract_version 1, aditivo).
- Dependencias nuevas: `langgraph>=1.2.10`, `langgraph-checkpoint-postgres>=3.1.2`
  (fijadas en `uv.lock`); tablas del checkpointer gestionadas por el saver y
  excluidas del drift de Alembic (`include_object` en `alembic/env.py`).
- Settings `AGENT_*/CHAT_*` (11 nuevos) registrados en `_known_fields`.

## Verificaciones

- `uv run ruff check` y `uv run ruff format --check` sobre las superficies del
  incremento: PASS (solo fallan 2 lint pre-existentes en `src/umbral/ops/`,
  ajenos al incremento).
- `uv run mypy` sobre `src` y tests del incremento: PASS (strict).
- `uv run pytest` (unit + contract + migration + architecture del incremento):
  PASS. Suite completa no-integración: 679 PASS; 6 fallos pre-existentes de
  entorno (Redis local, Railway, drift del OpenAPI committed, supabase),
  documentados como ajenos al incremento.
- Migración `0009`: renderiza SQL correcto offline (Alembic `--sql`) incluyendo
  el índice único parcial; test de migración determinista PASS; head del grafo
  actualizado a `0009_langgraph_runtime`.
- Integración (checkpointer, runtime e2e, aislamiento): PASS con Docker
  (testcontainers Postgres) vía `check-agent.ps1` (66 tests). Verificación
  local del drift en vivo: `alembic check` sobre una base recién migrada con
  tablas del checkpointer creadas por `saver.setup()` no reporta ninguna tabla
  langgraph (`include_object`, R-03); los `modify_default` de `version`/
  `actor_kind` que sí reporta son el patrón pre-existente del repo (afecta a
  todas las tablas, incluidas las de H2) y siguen la convención de las
  migraciones anteriores.

## Diferidos a seguimiento

- Gate completo desde checkout limpio en CI (convención de incrementos previos).
- Composición del runtime para producción (wiring API) — llega con H4.3.
- ADR de proveedor de modelo concreto — H4.4 (consistente con criteria).
