# Quickstart: Runtime LangGraph (H4.1)

**Feature**: 009-langgraph-runtime | **Date**: 2026-08-09

Validation guide. Implementation details live in `plan.md` and `tasks.md`.

## Prerequisites

- `.venv` activado y `uv sync --frozen --all-groups` (agrega `langgraph` y
  `langgraph-checkpoint-postgres`, R-01).
- Postgres con PostGIS/pgvector accesible para la integración (los tests de
  integración usan testcontainers según la convención de `check-silver.ps1`).
- `LANGGRAPH_STRICT_MSGPACK=true` (o `AGENT_STRICT_MSGPACK=true`) para el
  checkpointer (R-01, R-08).

## Escenarios

### 1. Conformance de contratos de agente

```powershell
uv run pytest tests/contract/test_agent_state_schema.py tests/contract/test_agent_graph_topology.py tests/contract/test_agent_reply_schema.py tests/contract/test_agent_chat_events.py -q
```

Expected: PASS. Verifica `contracts/agent/v1/*` contra el módulo de estado,
la topología v1 y el schema de reply, y los dos tipos de eventos de chat
nuevos en el registry (FR-004..FR-006, FR-010..FR-012).

### 2. Persistencia de sesiones y mensajes

```powershell
uv run pytest tests/unit/application/chat tests/integration/chat tests/migrations/test_0009_langgraph_runtime.py -q
```

Expected: PASS. Una sesión creada queda vinculada a usuario + search
profile; el historial se recupera en orden; los mensajes son inmutables
(0 reescrituras); un mensaje que supera `CHAT_MESSAGE_MAX_LENGTH` se
rechaza con error accionable; la migración `0009` aplica y hace rollback
(FR-001..FR-003, SC-001).

### 3. Runtime: ejecución, interrupción y reanudación sin duplicados

```powershell
uv run pytest tests/integration/agent -q
```

Expected: PASS. Con checkpointer Postgres (testcontainers) y
`FakeModelGateway`:

- Un turno corre hasta `completed` y persiste exactamente 1 mensaje de
  usuario y 1 de asistente.
- Al interrumpir a mitad de `generate_reply` (simulando desconexión), el
  estado queda `interrupted`, se reanuda con `attempt+1`, y los efectos ya
  aplicados NO se repiten (0 mensajes duplicados, FR-014, SC-005).
- Un mensaje del asistente solo existe cuando la respuesta se completa
  (0 mensajes parciales, R-11).
- Una segunda solicitud con un run `running` se rechaza con el error
  tipado `ChatExecutionInProgress` (FR-015, SC-005).

### 4. Aislamiento por usuario/sesión

```powershell
uv run pytest tests/integration/agent/test_runtime_isolation.py -q
```

Expected: PASS. Un usuario no puede crear turnos en sesiones de otro
usuario ni reanudar sus threads con ids manipulados; el aislamiento se
aplica en el servicio antes de tocar el checkpointer (FR-007, SC-003).

### 5. Model gateway: salidas estructuradas, timeout y reintentos

```powershell
uv run pytest tests/unit/infrastructure/agent -q
```

Expected: PASS. Con `ManagedModelGateway`: una respuesta fuera de
`reply-schema-v1` se rechaza o reintenta como máximo
`AGENT_MODEL_MAX_RETRIES` veces (0 inválidas al estado, FR-011); un
timeout agota el reintento acotado y queda un error tipado recuperable; el
uso (tokens) y las versiones de modelo/prompt/schema se registran por
llamada (FR-012, SC-004).

### 6. Retención: purga de checkpoints sin tocar historial

```powershell
uv run pytest tests/unit/infrastructure/agent/test_purge.py -q
```

Expected: PASS. `purge_agent_checkpoints(AGENT_CHECKPOINT_RETENTION_DAYS)`
borra los threads de sesiones inactivas más allá de la ventana y deja
intactas `chat_sessions`/`chat_messages` (FR-008, SC-003).

### 7. Arquitectura y harness completo

```powershell
uv run pytest tests/architecture/test_agent_boundaries.py -q
.\scripts\check-agent.ps1
.\scripts\check.ps1
```

Expected: PASS en los tres. `check-agent.ps1` queda registrado en
`check.ps1` (FR-019, SC-007); el test de arquitectura verifica que la capa
`agent` no salta los límites (R-03) y que `application/chat|agent` no
importa langgraph (Principio III).

## Verificación final

- Cerrar con `.\scripts\check.ps1` en verde desde checkout limpio y
  registrar evidencia consolidada en
  `docs/runbooks/evidence/langgraph-runtime-acceptance.md` (DoD #9),
  incluyendo los 7 escenarios de este quickstart y el diff de
  `contracts/events/v1/events-registry.json`.

## Resultado de validación (2026-08-09)

| Escenario | Resultado | Nota |
| --- | --- | --- |
| 1. Conformance de contratos de agente | PASS | 6 tests (state/topology/reply/events) |
| 2. Persistencia de sesiones y mensajes | PASS | unit + integración de repos (testcontainers) |
| 3. Runtime: ejecución/interrupción/reanudación | PASS | integración con checkpointer Postgres (testcontainers) |
| 4. Aislamiento por usuario/sesión | PASS | integración (testcontainers) |
| 5. Model gateway: salidas, timeout, reintentos | PASS | unit con httpx.MockTransport |
| 6. Retención: purga sin tocar historial | PASS | unit |
| 7. Arquitectura y harness | PASS | architecture + `check-agent.ps1` registrado en `check.ps1` |

Validación completa con Docker: `.\scripts\check-agent.ps1` PASS (66 tests,
incluidas las superficies de integración con testcontainers Postgres).
`.\scripts\check-migrations.ps1` PASS (offline upgrade/downgrade y metadata;
el drift en vivo queda SKIP sin `DATABASE_URL`). Verificación adicional del
drift en vivo: con las tablas del checkpointer creadas por `saver.setup()`,
`alembic check` no reporta ninguna tabla langgraph (R-03); los
`modify_default` de `version`/`actor_kind` son el patrón pre-existente del
repo (todas las tablas los tienen).

Settings nuevos: `AGENT_MODEL_PROVIDER` (fake), `AGENT_MODEL_NAME`,
`AGENT_MODEL_TIMEOUT_SECONDS` (30), `AGENT_MODEL_MAX_RETRIES` (2),
`AGENT_MANAGED_ENDPOINT`, `AGENT_MANAGED_API_KEY`, `AGENT_STATE_SCHEMA_VERSION`
(1), `AGENT_GRAPH_TOPOLOGY_VERSION` (1), `AGENT_PROMPT_VERSION`
(`agent-chat-v1`), `AGENT_REPLY_SCHEMA_VERSION` (`reply-v1`),
`AGENT_CHECKPOINT_RETENTION_DAYS` (30), `AGENT_STRICT_MSGPACK` (true) y
`CHAT_MESSAGE_MAX_LENGTH` (4000).
