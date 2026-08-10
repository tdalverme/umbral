# Tasks: Runtime LangGraph

**Input**: Design documents from `specs/009-langgraph-runtime/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice starts
with the failing contract/unit test named here"). En cada fase se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen solo trabajo compartido
(dependencias langgraph, settings `AGENT_*/CHAT_*`, contratos `agent/v1`,
migración `0009` con las 5 tablas, modelos/repos, el puerto `ModelGateway` con
el fake). US1 entrega la persistencia de sesiones/mensajes con eventos; US5 el
registro de graph/node/model-call runs; US4 el gateway gestionado con salidas
estructuradas; US3 el checkpointer Postgres, el aislamiento y la retención;
US2 (capstone) el estado v1, la topología y el runtime streaming/reanudable sin
duplicados; Polish el harness y el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar las dependencias langgraph, los settings `AGENT_*/CHAT_*`
y los contratos machine-checkable de agente (state-schema, graph-topology,
reply-schema) que usarán todas las historias.

- [X] T001 Añadir `langgraph` y `langgraph-checkpoint-postgres` (>=3.1.2) como
  dependencias runtime y fijarlas con `uv` (versiones exactas en `uv.lock`) en
  `pyproject.toml`
- [X] T002 [P] Definir el state schema v1 machine-checkable (registry_version
  `agent-state-schema-v1`, contract_version 1, schema_version 1, serializable
  true, fields: schema_version/messages/context/intent/pending_action/
  tool_results/errors) en `contracts/agent/v1/state-schema-v1.json`
- [X] T003 [P] Definir la graph topology v1 machine-checkable (topology_version
  1, entry `start`, nodes start/generate_reply/persist_reply, edges,
  tools `[]`, interrupts `[]`) en `contracts/agent/v1/graph-topology-v1.json`
- [X] T004 [P] Definir el reply schema v1 machine-checkable (reply_text
  1..2000, refs lista de `{entity, id}`) en
  `contracts/agent/v1/reply-schema-v1.json`
- [X] T005 [P] Añadir los settings `AGENT_*`/`CHAT_*` (`AGENT_MODEL_PROVIDER`
  fake, `AGENT_MODEL_NAME`, `AGENT_MODEL_TIMEOUT_SECONDS` 30,
  `AGENT_MODEL_MAX_RETRIES` 2, `AGENT_STATE_SCHEMA_VERSION` 1,
  `AGENT_GRAPH_TOPOLOGY_VERSION` 1, `AGENT_CHECKPOINT_RETENTION_DAYS` 30,
  `AGENT_STRICT_MSGPACK` true, `CHAT_MESSAGE_MAX_LENGTH` 4000) validados al
  iniciar y registrados en `_known_fields` en
  `src/umbral/infrastructure/config/settings.py` con su test unit en
  `tests/unit/config/`

**Checkpoint**: dependencias, settings y contratos publicados; las historias
tienen versiones y límites disponibles.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Capa de datos compartida (migración `0009`, 5 tablas, modelos y
repositorios), el filtro de exclusión de tablas del checkpointer en Alembic y
el puerto `ModelGateway` con el fake. Nada de las historias comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T006 Escribir el test de migración: `0009_langgraph_runtime` aplica y
  hace rollback, crea las 5 tablas, los ENUMs, el índice único parcial
  `uq_agent_graph_runs_session_active` y las FK; verifica que las tablas de
  langgraph NO están en nuestra metadata en
  `tests/migrations/test_0009_langgraph_runtime.py`
- [X] T007 [P] Escribir los unit tests del puerto `ModelGateway` y del fake:
  reply estructurado determinista que cumple `reply-schema-v1`, registra
  usage y versiones, 0 proveedor en el dominio en
  `tests/unit/application/agent/test_model_gateway.py`

### Implementation for Foundational

- [X] T008 Añadir el filtro `include_object` en `alembic/env.py` para excluir
  las tablas del checkpointer de langgraph del autogenerate/drift
- [X] T009 [P] Definir los modelos de chat: `ChatSessionRow` (user_id FK,
  search_profile_id FK, status ENUM `chat_session_state`, mixin de auditoría,
  índices) y `ChatMessageRow` (session_id FK, role ENUM `chat_message_role`,
  content JSONB, state ENUM `chat_message_state`, graph_run_id FK nullable,
  inmutable) en `src/umbral/infrastructure/db/models/chat.py`
- [X] T010 [P] Definir los modelos de runs: `AgentGraphRunRow`
  (state_schema_version, topology_version, status ENUM `agent_run_state`,
  attempt, started_at/finished_at, error_summary JSONB, token_usage JSONB,
  correlation_id; índice único parcial `uq_agent_graph_runs_session_active`),
  `AgentNodeRunRow` (node_name, node_kind ENUM `agent_node_kind`, status,
  latencia, error_summary, usage, correlation_id) y `AgentModelCallRow`
  (model/prompt/schema_version, status ENUM `agent_call_state`, tokens,
  latency_ms, error_code, correlation_id) en
  `src/umbral/infrastructure/db/models/agent.py`
- [X] T011 Escribir la migración `0009_langgraph_runtime` (crea `chat_sessions`,
  `chat_messages`, `agent_graph_runs`, `agent_node_runs`, `agent_model_calls`
  con ENUMs, índice único parcial, FKs e índices) en
  `alembic/versions/0009_langgraph_runtime.py`
- [X] T012 [P] Implementar los repositorios de chat (`ChatSessionRepository`:
  create, get_by_id scoped por usuario, list_by_user; `ChatMessageRepository`:
  append inmutable, list_ordered) en
  `src/umbral/infrastructure/db/repositories/chat.py`
- [X] T013 [P] Implementar los repositorios de runs (`GraphRunRepository`: claim
  vía índice único parcial, marcar status/attempt/latencia/usage, get by id;
  `NodeRunRepository`: insert; `ModelCallRepository`: insert) en
  `src/umbral/infrastructure/db/repositories/agent.py`
- [X] T014 [P] Definir el puerto `ModelGateway` (`generate_structured(messages,
  schema, schema_version, prompt_version, model_version) -> ModelResult` con
  contenido validado, usage, latencia, status) y el `FakeModelGateway`
  (respuesta determinista, 0 proveedor) en
  `src/umbral/application/agent/ports.py` y
  `src/umbral/infrastructure/agent/model_gateway/fake.py`

**Checkpoint**: capa de datos, exclusión Alembic y gateway port/fake listos y
verificados; las historias pueden comenzar.

---

## Phase 3: User Story 1 — Conversacion persistente ligada al radar (Priority: P0) MVP

**Goal**: el usuario crea una sesión ligada a su radar (usuario + search
profile) que persiste; el historial se recupera en orden con roles y contenido
permitido; los mensajes son inmutables y con límites; el estado refleja el del
search profile; cada creación emite su evento de producto.

**Independent Test**: crear una sesión la vincula a usuario + search profile;
el historial se recupera en orden; 0 mensajes se reescriben; un mensaje que
supera `CHAT_MESSAGE_MAX_LENGTH` se rechaza con error accionable; una sesión de
un radar pausado/archivado rechaza mensajes nuevos pero conserva el historial;
los eventos `chat.session_created.v1`/`chat.message_created.v1` se validan
(SC-001).

### Tests for User Story 1

> Escribir T015–T017 primero y confirmar que fallan por la conducta ausente.

- [X] T015 [P] [US1] Escribir los unit tests del chat service (crear sesión
  ligada a usuario+profile, acceso denegado a sesión ajena, historial en orden,
  inmutabilidad con 0 reescrituras, límite de longitud rechazado, estado
  espejo del profile, rechazo de turnos en pausada/archivada) en
  `tests/unit/application/chat/test_service.py`
- [X] T016 [P] [US1] Escribir el test de integración de los repositorios de
  chat contra Postgres (testcontainers): create, append en orden, lookups
  scoped por ownership en `tests/integration/chat/test_session_repo.py`
- [X] T017 [P] [US1] Escribir la conformance del events registry:
  `chat.session_created.v1` y `chat.message_created.v1` aceptados, tipos
  desconocidos rechazados, 0 claves PII en payloads en
  `tests/contract/test_agent_chat_events.py`

### Implementation for User Story 1

- [X] T018 [P] [US1] Actualizar aditivamente el events registry con
  `chat.session_created.v1` y `chat.message_created.v1` (contract_version 2)
  en `contracts/events/v1/events-registry.json`
- [X] T019 [US1] Definir los valores/errores de chat (`ChatSession`,
  `ChatMessage`, `MessageRole` user/assistant/system, `MessageContent` text|ref
  tipado, `ChatSessionState` active/paused/archived, errores tipados
  `ChatMessageTooLong`, `ChatSessionNotActive`, `ChatSessionNotFound`) en
  `src/umbral/application/chat/contracts.py`
- [X] T020 [P] [US1] Definir los puertos de repositorio de chat
  (`ChatSessionRepository`, `ChatMessageRepository`) en
  `src/umbral/application/chat/ports.py`
- [X] T021 [US1] Implementar el chat service (`create_session` emitiendo
  `chat.session_created.v1`, `get_session` scoped por ownership,
  `list_history` en orden, `append_user_message`, `persist_assistant_message`
  emitiendo `chat.message_created.v1`, `assert_accepts_turn` con estado espejo
  del profile y límite de longitud) en `src/umbral/application/chat/service.py`

**Checkpoint**: sesiones y mensajes persistentes, auditables y con eventos;
US1 cerrada.

---

## Phase 4: User Story 5 — Ejecuciones auditables (Priority: P0)

**Goal**: cada graph run registra version de schema/topologia, estado,
latencia, errores resumidos, uso y correlacion; cada node run queda vinculado
al graph run; cada model call registra versiones y uso; 0 PII en summaries.

**Independent Test**: escenarios de exito, interrupcion y fallo dejan el 100%
de los runs registrados con los campos requeridos y correlacion estable;
ningun summary contiene contenido de conversacion (SC-006).

### Tests for User Story 5

> Escribir T022 primero y confirmar que falla por la conducta ausente.

- [X] T022 [P] [US5] Escribir los unit tests del run recorder (records
  idempotentes por id, error_summary/usage sin contenido, correlacion
  preservada entre run/nodes/calls) en
  `tests/unit/application/agent/test_run_recorder.py`

### Implementation for User Story 5

- [X] T023 [US5] Definir los valores/errores de runs (`GraphRun`, `NodeRun`,
  `ModelCall`, estados de run/node/call, `RunError` tipado) en
  `src/umbral/application/agent/contracts.py`
- [X] T024 [P] [US5] Definir los puertos de repositorio de runs
  (`GraphRunRepository`, `NodeRunRepository`, `ModelCallRepository`) en
  `src/umbral/application/agent/ports.py`
- [X] T025 [US5] Implementar el run recorder (`record_graph_run`,
  `record_node_run`, `record_model_call`; idempotente por id; solo
  error_summary/usage/correlacion, 0 contenido) en
  `src/umbral/application/agent/service.py`

**Checkpoint**: ejecuciones auditables y trazables; US5 cerrada.

---

## Phase 5: User Story 4 — Modelo centralizado con salidas estructuradas (Priority: P0)

**Goal**: toda llamada al modelo pasa por un adapter unico con salidas
estructuradas validadas contra `reply-schema-v1`, timeout, reintentos acotados
y registro de uso/versiones; 0 respuestas invalidas llegan al estado; 0 codigo
de dominio conoce proveedores.

**Independent Test**: una respuesta fuera de schema se rechaza o reintenta como
maximo `AGENT_MODEL_MAX_RETRIES` veces (0 invalidas al estado); un timeout
agota el reintento acotado con error tipado recuperable; el 100% de las
llamadas registra versiones de modelo/prompt/schema y uso (SC-004).

### Tests for User Story 4

> Escribir T026–T027 primero y confirmar que fallan por la conducta ausente.

- [X] T026 [P] [US4] Escribir la conformance del reply schema (parse/validacion,
  round-trip, invalidos rechazados) en `tests/contract/test_agent_reply_schema.py`
- [X] T027 [P] [US4] Escribir los unit tests del `ManagedModelGateway` (reply
  valido pasa; output invalido reintentado `<=AGENT_MODEL_MAX_RETRIES` y luego
  error tipado; timeout agota el reintento acotado con estado recuperable;
  usage y versiones registrados por llamada) en
  `tests/unit/infrastructure/agent/test_managed_gateway.py`

### Implementation for User Story 4

- [X] T028 [US4] Implementar el `ManagedModelGateway` (HTTP structured output
  espejo del criteria managed extractor, timeout `AGENT_MODEL_TIMEOUT_SECONDS`,
  reintento acotado con backoff `AGENT_MODEL_MAX_RETRIES`, validacion contra
  `reply-schema-v1`, registro de usage y versiones) en
  `src/umbral/infrastructure/agent/model_gateway/managed.py`

**Checkpoint**: gateway gestionado con salidas estructuradas verificado;
US4 cerrada.

---

## Phase 6: User Story 3 — Aislamiento y continuidad entre requests (Priority: P0)

**Goal**: los checkpoints persisten entre requests aislados por usuario/sesion
con `setup()` seguro (strict msgpack); la retencion purga threads inactivos por
mas de `AGENT_CHECKPOINT_RETENTION_DAYS` sin tocar historial; la politica queda
documentada y versionada.

**Independent Test**: el checkpointer persiste y reanuda threads; el 100% de
los intentos de acceso cruzado se deniega antes de tocar el checkpointer; la
purga borra solo threads inactivos fuera de la ventana y deja intactas
`chat_sessions`/`chat_messages`; es idempotente (SC-003).

### Tests for User Story 3

> Escribir T029–T030 primero y confirmar que fallan por la conducta ausente.

- [X] T029 [P] [US3] Escribir los tests de integración del checkpointer
  (testcontainers): `saver.setup()` crea sus tablas, save/load/resume de un
  thread, aislamiento por thread id, strict msgpack en
  `tests/integration/agent/test_checkpointer.py`
- [X] T030 [P] [US3] Escribir los unit tests de la purga (borra solo threads de
  sesiones inactivas fuera de la ventana, 0 toques a tablas de chat,
  idempotente) en `tests/unit/infrastructure/agent/test_purge.py`

### Implementation for User Story 3

- [X] T031 [US3] Implementar la fabrica del checkpointer Postgres (`PostgresSaver`
  con `setup()`, autocommit + dict_row, strict msgpack via
  `AGENT_STRICT_MSGPACK`, helper de borrado de thread) en
  `src/umbral/infrastructure/agent/checkpointer.py`
- [X] T032 [P] [US3] Implementar `purge_agent_checkpoints(retention_days)`
  (busca sesiones inactivas fuera de la ventana, borra sus threads de
  checkpoint, 0 toque a tablas de chat, idempotente) en
  `src/umbral/infrastructure/agent/purge.py`
- [X] T033 [P] [US3] Registrar `purge_agent_checkpoints` como duty de
  mantenimiento del scheduler (orden recovery-first) en
  `src/umbral/workers/scheduler.py`

**Checkpoint**: checkpointer, aislamiento y retencion verificados; US3 cerrada.

---

## Phase 7: User Story 2 — Ejecucion reanudable sin efectos duplicados (Priority: P0) CAPSTONE

**Goal**: el runtime orquesta estado v1 + topologia v1 + gateway + checkpointer:
emite eventos tipados, reanuda desde el ultimo checkpoint tras interrupcion y
nunca repite efectos (0 duplicados, 0 mensajes parciales); una segunda solicitud
a una sesion con run activo se rechaza con `ChatExecutionInProgress`.

**Independent Test**: un turno completo persiste exactamente 1 mensaje de
usuario y 1 de asistente; interrumpir a mitad de `generate_reply` deja el run
`interrupted`, la reanudacion usa `attempt+1` y 0 efectos se repiten; 0
mensajes parciales en el historial; una segunda solicitud con run `running` se
rechaza con error tipado (SC-002, SC-005).

### Tests for User Story 2

> Escribir T034–T039 primero y confirmar que fallan por la conducta ausente.

- [X] T034 [P] [US2] Escribir la conformance del state schema (contrato vs
  modulo de estado, round-trip JSON-safe, mismatch de schema_version como error
  tipado o migracion documentada) en `tests/contract/test_agent_state_schema.py`
- [X] T035 [P] [US2] Escribir la conformance de la graph topology (el builder
  produce exactamente nodes/edges/entry v1, `tools == []` e `interrupts == []`)
  en `tests/contract/test_agent_graph_topology.py`
- [X] T036 [P] [US2] Escribir los unit tests del estado (serialize/deserialize
  JSON-safe, ledger `effects_applied` dentro de context) en
  `tests/unit/agent/test_state.py`
- [X] T037 [P] [US2] Escribir los unit tests del graph (MemorySaver +
  FakeModelGateway: el run completa; el ledger evita reaplicar efectos en
  resume) en `tests/unit/agent/test_graph.py`
- [X] T038 [P] [US2] Escribir los tests e2e del runtime (testcontainers): turno
  completo con 1+1 mensajes; interrupcion en `generate_reply` → `interrupted`,
  resume con `attempt+1` y 0 mensajes duplicados/parciales; solicitud
  concurrente rechazada con `ChatExecutionInProgress` en
  `tests/integration/agent/test_runtime_e2e.py`
- [X] T039 [P] [US2] Escribir los tests de aislamiento del runtime (acceso
  cruzado con ids manipulados denegado antes de tocar el checkpointer) en
  `tests/integration/agent/test_runtime_isolation.py`

### Implementation for User Story 2

- [X] T040 [US2] Implementar el state schema v1 (`StateV1` con
  messages/context/intent/pending_action/tool_results/errors/schema_version,
  serialize/deserialize JSON-safe) en `src/umbral/agent/state.py`
- [X] T041 [P] [US2] Definir los eventos tipados de runtime (`RunStarted`,
  `ReplyFragment`, `RunCompleted`, `RunFailed`, `RunInterrupted` con
  correlacion) en `src/umbral/agent/events.py`
- [X] T042 [US2] Implementar `build_topology_v1` (StateGraph:
  start → generate_reply → persist_reply; gateway + saver + sinks por
  constructor; efectos aplicados via el helper `apply_effect` del ledger) en
  `src/umbral/agent/graph.py`
- [X] T043 [US2] Implementar el runtime (`run_turn`/resume: claim del run via
  indice unico parcial, emision de eventos tipados, persistencia de mensajes
  via chat service, registro de runs via run recorder, resume con `attempt+1`,
  rechazo `ChatExecutionInProgress`, 0 mensajes parciales persistidos) en
  `src/umbral/agent/runtime.py`

**Checkpoint**: runtime reanudable sin duplicados verificado de punta a punta;
US2 cerrada.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: harness dedicado, límites de arquitectura del layer `agent`,
verificación de 0 superficies HTTP/tools, evidencia de cierre y gate completo.
Nada de esto cambia el comportamiento de producto.

- [X] T044 Escribir el test de que el harness cubre las superficies de agent y
  que 0 endpoints HTTP de chat, 0 tools y 0 UI se agregan por el incremento en
  `tests/contract/test_agent_harness.py`
- [X] T045 [P] Escribir los tests de límites de arquitectura del layer `agent`
  (agent→application/infra permitido; `application/chat` y `application/agent`
  y `domain` 0 imports de langgraph; `api/`/workers aun no importan el runtime)
  en `tests/architecture/test_agent_boundaries.py`
- [X] T046 [P] Crear `scripts/check-agent.ps1` (pytest de conformance agent,
  chat service, run recorder, gateway, purge, integración agent/chat, migración
  0009 y arquitectura agent) y registrarlo con el guard `agentSurface` en
  `scripts/check.ps1`
- [X] T047 [P] Escribir la evidencia de cierre del incremento en
  `docs/runbooks/evidence/langgraph-runtime-acceptance.md` (resultado de cada SC
  del spec y recorrido de los escenarios de
  `specs/009-langgraph-runtime/quickstart.md`)
- [X] T048 [P] Actualizar el quickstart del feature con el resultado real de
  cada escenario y los settings `AGENT_*/CHAT_*` en
  `specs/009-langgraph-runtime/quickstart.md`
- [X] T049 Verificar el gate completo desde checkout limpio: `uv sync --frozen
  --all-groups`, `uv run ruff format --check .`, `uv run ruff check .`,
  `uv run mypy src tests`, `uv run pytest`, `uv run alembic current --check-heads`,
  `uv run alembic check` y `.\scripts\check.ps1`; documentar el resultado en la
  evidencia de cierre

---

## Dependencies

- **Setup (Phase 1)**: sin dependencias; publica deps, settings y contratos.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias
  (capa de datos + gateway port/fake).
- **US1 (P0)**: depende de Foundational (modelos/repos de chat, T009/T012);
  independiente de US2–US5.
- **US5 (P0)**: depende de Foundational (modelos/repos de runs, T010/T013);
  independiente de US1/US2/US3/US4.
- **US4 (P0)**: depende de Setup (reply-schema, T004) y Foundational (puerto +
  fake, T014); independiente de US1/US2/US3/US5.
- **US3 (P0)**: depende de Foundational (modelos de chat para la purga, T009) y
  Setup (settings de retención, T005); independiente de US1/US2/US4/US5.
- **US2 (P0, capstone)**: depende de US1 (chat service), US5 (run recorder),
  US4 (gateway), US3 (checkpointer) y Foundational; es la última historia.
- **Polish (final)**: depende de las historias deseadas (T044–T048 son
  paralelizables con las historias tardías).

### User Story Dependencies

- **US1**: modelos/repos de chat (T009/T012) + service (T021) + eventos (T018).
- **US5**: modelos/repos de runs (T010/T013) + recorder (T025).
- **US4**: puerto/fake (T014) + managed (T028) + reply schema (T004).
- **US3**: checkpointer (T031) + purga (T032) + scheduler (T033).
- **US2**: compone chat service + run recorder + gateway + checkpointer en
  `runtime.py` (T043); antes necesita estado (T040), eventos (T041) y graph
  (T042).
- Trabajo secuencial recomendado: US1 → US5 → US4 → US3 → US2 → Polish.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Contratos/valores antes del service/runtime; conformance al final de la
  historia.
- Historia completa y verificada antes de pasar a la siguiente.

### Parallel Opportunities

- T002/T003/T004/T005 en Setup; T007, T009/T010/T012/T013/T014 en Foundational;
  T015/T016/T017, T018/T019/T020 en US1; T022, T023/T024 en US5;
  T026/T027, T028 en US4; T029/T030, T031/T032/T033 en US3;
  T034/T035/T036/T037/T038/T039, T040/T041 en US2; T044/T045/T046/T047/T048 en
  Polish — tocan archivos distintos sin dependencias.
- Tras Foundational, US1, US5, US4 y US3 pueden empezar en paralelo; US2 los
  integra; Polish puede preparar harness en paralelo con US3/US2.

---

## Parallel Example: User Story 2

```bash
# Tests de US2 en paralelo:
Task: "Conformance de state schema en tests/contract/test_agent_state_schema.py"
Task: "Conformance de graph topology en tests/contract/test_agent_graph_topology.py"
Task: "Unit tests del estado en tests/unit/agent/test_state.py"
Task: "Unit tests del graph en tests/unit/agent/test_graph.py"
Task: "E2E del runtime en tests/integration/agent/test_runtime_e2e.py"
Task: "Isolation del runtime en tests/integration/agent/test_runtime_isolation.py"

# Implementación (única por fase, en orden):
Task: "state.py → events.py → graph.py → runtime.py"
```

---

## Implementation Strategy

### MVP First (Camino crítico P0 del backlog)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar US1 (persistencia de sesiones/mensajes): cubre UM-H4-001.
4. **STOP y VALIDAR** cada historia con su Independent Test antes de continuar.
5. Primer recorrido interno del hito: US1 + harness de agent (T046 parcial).
6. Demo/entrega si corresponde; US5, US4, US3 y US2 (capstone) después.

### Incremental Delivery

1. Setup + Foundational → deps, settings, contratos, capa de datos y gateway
   port/fake listos.
2. US1 → sesiones/mensajes persistentes con eventos → demo (MVP).
3. US5 → runs auditables → validar.
4. US4 → gateway gestionado → validar.
5. US3 → checkpointer, aislamiento y retención → validar.
6. US2 → estado/topología/runtime streaming y reanudable → validar (capstone
   UM-H4-002/005).
7. Polish → harness, arquitectura, evidencia de cierre.

### Parallel Team Strategy

1. Equipo completo Setup + Foundational juntos.
2. Tras Foundational: US1, US5, US4 y US3 en paralelo (tocan capas distintas).
3. Tras esas cuatro: US2 integra el runtime (capstone).
4. Polish prepara harness y arquitectura en paralelo con US3/US2.
5. Las historias integran sin romperse (contratos, tablas y tests separados; la
   migración 0009 es única y se cierra en Foundational).

---

## Notes

- [P] = archivos distintos, sin dependencias de tareas incompletas.
- [Story] mapea cada tarea a su historia (`spec.md`) para trazabilidad.
- Cada historia es independientemente completa y testeable.
- Verificar que los tests fallen antes de implementar.
- Commit después de cada tarea o grupo lógico.
- Detenerse en cualquier checkpoint para validar la historia sola.
- Evitar: tareas vagas, conflictos de archivo, dependencias entre historias que
  rompan la independencia.
- Dependencias nuevas SOLO las de T001 (`langgraph`,
  `langgraph-checkpoint-postgres`); nada mas se agrega (R-01).
- 0 contratos HTTP de chat, 0 tools, 0 UI en este incremento (FR-020, T044).
- Los checkpoints son estado operativo: nunca fuente de verdad (R-02); las
  tablas de langgraph son gestionadas por el saver y excluidas de Alembic
  (R-03, T008/T006).
- Reanudacion sin duplicados via ledger `effects_applied` en `context` (R-04,
  FR-014, clarificacion 2026-08-09): solo respuestas completas se persisten
  (R-11); una segunda solicitud con run activo se rechaza con
  `ChatExecutionInProgress` (R-06, FR-015).
- El estado de la sesion refleja el del search profile (R-12, FR-001); 0
  transiciones propias.
- Retencion: sesiones/mensajes con la cuenta; checkpoints purgados tras
  `AGENT_CHECKPOINT_RETENTION_DAYS` (clarificacion 2026-08-09, FR-008, R-09).
- El proveedor de modelo queda diferido: `AGENT_MODEL_PROVIDER` default `fake`;
  el ADR de proveedor es de H4.4 (R-05).
- Runs, nodes, model calls, eventos y reportes sin PII: solo ids, versiones,
  conteos, codigos y correlacion (FR-018).
- `LANGGRAPH_STRICT_MSGPACK=true` / `AGENT_STRICT_MSGPACK=true` obligatorio en
  el checkpointer (R-01, R-08).
- Los events de producto nuevos son exactamente `chat.session_created.v1` y
  `chat.message_created.v1` (R-07, DoD #4).
- El layout del layer `agent` sigue el contrato import-linter ya existente
  (`agent | api | workers`); `application/chat` y `application/agent` no
  importan langgraph (Principio III, T045).
