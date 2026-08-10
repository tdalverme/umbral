# Research: Tools explicitas y permisos (H4.2)

**Feature**: 010-agent-tools | **Date**: 2026-08-09

Decisions taken during planning. Each entry records the decision, the
rationale, and the alternatives considered.

## R-01 — Tool dispatch: registry versionado y executor comun; sin ToolNode de LangGraph

**Decision**: Las tools se declaran en un contrato versionado
(`contracts/agent/tools/tool-contract-v1.json`) y se ejecutan mediante un
registry + executor comun en la capa `agent` (`agent/tools/`): el executor
valida identidad, search scope, schema de argumentos, timeout, idempotencia
y redaccion de salidas para TODA tool, y registra cada invocacion como fila
`agent_node_runs` con `node_kind='tool'` (discriminator ya presente en la
migracion 0009, R-10 de H4.1). Un nodo del graph (`run_tools`) ejecuta las
`tool_calls` pendientes del estado; la compilacion de intencion a
`tool_calls` es de H4.3, pero el mecanismo de ejecucion y su contrato se
prueban en este incremento.

**Rationale**: La constitucion exige tools internas explicitas y
permissionadas con contratos versionados, y FR-001..FR-004 exigen validacion
uniforme, redaccion, timeout y registro de tool runs. Un registry propio
mantiene el contrato como fuente de verdad (versionado, conformance-checked,
redaccion por schema) y es deterministico de probar sin LLM; la suite de
abuso (UM-H4-016) se ejecuta contra el executor, no contra un modelo.

**Alternatives considered**:
- `langgraph` ToolNode / `bind_tools`: acopla el contrato al formato de
  tools del proveedor, complica versionar/redactar y agrega maquinaria que
  H4.3 no necesita; rechazado.
- Nodos que llaman servicios directo desde `_generate_reply`: sin validacion
  comun ni registro por tool; rechazado (FR-004).

## R-02 — Schemas de agente v2: state/topology/reply; checkpoints v1 declarados incompatibles

**Decision**: Se crean `contracts/agent/v2/state-schema-v2.json`,
`graph-topology-v2.json` y `reply-schema-v2.json` (los archivos v1 quedan
intactos como version auditada). Cambios minimos:

- `state-schema-v2`: agrega `tool_calls: list[tool_call]` y define el item de
  `tool_results` (tool, status, result/error redactado); `pending_action`
  puede poblarse con una referencia a propuesta.
- `graph-topology-v2`: `start → generate_reply → (si tool_calls → run_tools
  → generate_reply, loop acotado por `AGENT_TOOLS_MAX_CALLS_PER_TURN`
  default 5) → persist_reply`; `tools: [8 nombres]`.
- `reply-schema-v2`: agrega `tool_calls: list[{tool, args}]` (0..N acotado).

Los checkpoints v1 se declaran incompatibles con error tipado
(`AgentStateIncompatible`) al reanudar, segun FR-009 de H4.1 (migrar o
declarar incompatibles de forma documentada): los checkpoints son estado
operativo de ventana corta (R-09 de H4.1) y una migracion v1→v2 seria
especulativa.

**Rationale**: FR-004/FR-005 (schema versionado y serializable) y FR-001
(contrato comun). El loop acotado es el seam que H4.3 consume y el minimo
que hace demostrable la ejecucion E2E de una tool.

**Alternatives considered**: mutar los contratos v1 in-place: rechazado —
los runs previos registran sus versiones y no se mutan (principio II/V).
Migrar checkpoints v1→v2 automaticamente: rechazado — ventana corta,
migracion especulativa sin driver de producto.

## R-03 — Propuesta de perfil durable: tabla nueva en migracion 0010_agent_tools

**Decision**: `search_profile_update_proposals` (nueva, migracion
`0010_agent_tools`): `id`, `session_id` FK, `search_profile_id` FK,
`base_profile_version` int, `diff` JSONB (diff validado), `impact` JSONB,
`state` ENUM `proposal_state` (`pending`/`approved`/`rejected`),
`expires_at`, `applied_idempotency_key` nullable (un solo uso; replay con la
misma key devuelve el mismo resultado), `created_by` (actor audit), mixin de
auditoria. Indice unico parcial `uq_proposals_profile_idempotency
(search_profile_id, applied_idempotency_key) WHERE applied_idempotency_key
IS NOT NULL`. Retencion: mientras exista la cuenta (clarificacion Q1).

**Rationale**: Clarificaciones Q1/Q2 (propuestas durables y auditables con
ciclo de vida determinista) y FR-008/FR-010. El `base_profile_version`
soporta la obsolescencia (clarificacion Q1).

**Alternatives considered**: propuestas solo en checkpoint: rechazado por la
clarificacion Q1 (decisión durable y auditable). Propuesta como JSON en
`pending_action` con copia en tabla: rechazado — dos fuentes de verdad.

## R-04 — apply delegado a RadarService.update_profile; obsolescencia = ConcurrencyConflict

**Decision**: La tool `apply_search_profile_update` valida la propuesta
(misma sesion, `pending`, sin expirar, `base_profile_version` == version
vigente del perfil) y aplica el diff mediante
`RadarService.update_profile(expected_version=base_profile_version)` — el
mismo camino H3-030: versiona el perfil, crea snapshot, emite evento y
dispara la recomputacion preservando el run anterior. Un
`ConcurrencyConflict` (la version vigente ya no es la base) rechaza la
propuesta por obsolescencia con error tipado (clarificacion Q1). Al exito la
propuesta pasa a `approved` (un solo uso) y se registra
`applied_idempotency_key`.

**Rationale**: Cero logica de versionado/recomputacion duplicada: el radar
ya implementa el optimistic lock y el submit de run (H3-030). La validacion
del diff contra policy/schema la hace el propio camino de `update_profile`.

**Alternatives considered**: reimplementar versionado en la tool: rechazado
— duplica la maquinaria existente. Rebase automatico del diff: rechazado por
la clarificacion Q1 (obsolescencia).

## R-05 — Idempotencia de apply sobre la propuesta (un solo uso) + clave

**Decision**: La idempotency key de apply se guarda en
`applied_idempotency_key` de la propuesta. Primer apply con la propuesta
`pending`: ejecuta y la deja `approved` con su key. Replay con la MISMA key:
devuelve el resultado ya registrado (0 duplicados de version/run/evento).
Replay con OTRA key o propuesta ya usada: error tipado, 0 efectos (FR-012).
El indice unico parcial es el enforcement de DB.

**Rationale**: FR-012 (repetir con la misma key no duplica) y la
clarificacion Q1 (un solo uso). Reutiliza el patron de idempotencia del
feedback (H3.3) sin maquinaria nueva.

**Alternatives considered**: tabla de fingerprints separada: rechazado — la
propuesta ya es el objeto durable; anclar la key ahi es el minimo.

## R-06 — Herramientas de lectura delegan en servicios existentes

**Decision**: `get_search_profile` → `RadarService.get_profile` +
`CriteriaService.latest_compilation` (criterios ejecutables) + estado del
radar; `find_matches` → `RadarService.get_matches` (estrictamente read-only:
ultimo run succeeded, overlay de decision states, paginacion estable; sin
run → estado explicito, FR-014); `explain_match` → `ScoringService.
get_explanation` (explicacion recompuesta de evaluations congeladas, 0
afirmaciones nuevas); `compare_listings` → `ScoringService.build_comparison`
(validacion de pertenencia y limite incluida). Ninguna de estas tools
persiste ni dispara jobs.

**Rationale**: El spec (FR-005/013/015/017) exige que las tools sean
delgadas sobre el motor deterministico: los servicios de H2.3/H3.2 ya
implementan ownership, runs congelados, explicaciones y comparacion.

**Alternatives considered**: consultas directas de la tool a repositorios:
rechazado — violaria la direccion de dependencias y el deny-by-default.

## R-07 — record_feedback mapea a FeedbackService.record_feedback (like/dislike)

**Decision**: La tool `record_feedback` acepta solo `like`/`dislike` con
`reason_keys` opcionales (clarificacion Q3, FR-019) y delega en
`FeedbackService.record_feedback(idempotency_key=...)`: idempotencia
(noop si la key existe), supersede con compensacion trazable al cambiar
decision, emision de `feedback.recorded.v1` y evaluacion de aprendizaje que
puede crear una `LearningProposal` (devuelta en el resultado de la tool).
Tipos fuera de contrato (`save`/`dismiss`/`contacted`) se rechazan en la
validacion del executor con error tipado.

**Rationale**: FR-019/FR-020 y la clarificacion Q3; el servicio de H3.3 ya
implementa idempotencia, compensacion y propuestas.

**Alternatives considered**: contrato amplio con todos los tipos de H3.3:
rechazado por la clarificacion Q3.

## R-08 — search_urban_context necesita un seam de lectura nuevo (P1)

**Decision**: Se agrega un metodo de lectura en `application/criteria`:
`list_urban_signals(listing_id)` (el puerto `UrbanSignalRepository.
list_for_listing` ya existe pero no esta expuesto por servicio ni filtra
precision). La tool respeta la politica de precision existente
(`_authorized_geometry`: solo `exact`/`block` producen coordenadas; el resto
devuelve `None`) y la redaccion del registry (forbidden_keys incluye
`geometry`): las coordenadas se omiten cuando la precision autorizada no
aplica, y 0 datos inventados ante ausencia de signals (FR-021).

**Rationale**: FR-021 exige signals versionadas con fuente/fecha/geometria/
algoritmo y precision respetada; el adapter SQLAlchemy ya devuelve esos
campos. El seam de lectura es el minimo necesario.

**Alternatives considered**: consultar el repo desde la tool: rechazado —
misma violacion de capas que R-06.

## R-09 — Eventos de producto: propuesta creada y aplicada; tool runs quedan en tablas

**Decision**: Aditivo al events registry: `search_profile.update_proposed.v1`
(keys: `proposal_id`, `search_profile_id`, `base_profile_version`) y
`search_profile.update_applied.v1` (keys: `proposal_id`,
`search_profile_id`, `profile_version`). Las invocaciones de tools NO emiten
eventos de producto: quedan auditadas en `agent_node_runs`
(`node_kind='tool'`), igual que los graph runs en H4.1 (R-07 de H4.1 —
machinery operativa, no estado de producto). La version del registry se
bumpa de forma aditiva segun el estado real del archivo al implementar
(hoy `contract_version "1"` con los tipos de chat presentes).

**Rationale**: DoD #4 — proponer/aplicar un cambio de perfil es cambio de
estado de producto y debe auditarse como evento; una invocacion de tool es
machinery operativa cuyo rastro es el tool run.

**Alternatives considered**: evento por invocacion de tool: rechazado —
duplicaria la auditoria de `agent_node_runs`. 0 eventos nuevos: rechazado —
violaria DoD #4 para el ciclo de propuestas.

## R-10 — Settings AGENT_TOOLS_* planos y registrados

**Decision**: `AGENT_TOOLS_STATE_SCHEMA_VERSION` (2),
`AGENT_TOOLS_TOPOLOGY_VERSION` (2), `AGENT_TOOLS_CONTRACT_VERSION` (`v1`),
`AGENT_TOOLS_MAX_CALLS_PER_TURN` (5), `AGENT_TOOLS_TIMEOUT_SECONDS` (10),
`AGENT_TOOLS_OUTPUT_MAX_ITEMS` (20), `AGENT_PROPOSAL_TTL_HOURS` (24).
Todas en `Settings` con alias de env, `_known_fields` y tests de config
(`tests/unit/config/test_agent_settings.py`, requerido por el harness).

**Rationale**: Convencion del repo (R-08 de H4.1): env planas con prefijo de
dominio, validacion al startup, defaults seguros. La TTL de propuestas es la
ventana de vencimiento (policy, clarificacion Q2).

**Alternatives considered**: settings anidadas: rechazado — rompe la
convencion plana.

## R-11 — Vencimiento de propuestas como scheduler maintenance duty

**Decision**: `infrastructure/agent/proposals/expire.py` implementa
`expire_search_profile_proposals(ttl_hours)` (pending con `expires_at`
pasado → `rejected` con motivo `expired`), registrada como maintenance duty
en `workers/scheduler.py` junto a `purge_agent_checkpoints` (orden
recovery-first). Idempotente (repetir es no-op) y nunca toca el perfil.

**Rationale**: Clarificacion Q2 (transiciones deterministas: rechazo solo
por obsolescencia o vencimiento) y FR-009. Patron identico al purge de
checkpoints (R-09 de H4.1).

**Alternatives considered**: rechazo lazy al aplicar (solo validar
`expires_at` al apply): se hace igual en apply, pero sin el duty las
propuestas quedarian "pendientes" indefinidamente en auditoria; el duty da
estado cerrado y consultable.

## R-12 — Composicion en infrastructure/agent/composition.py; 0 HTTP

**Decision**: Se agrega `infrastructure/agent/composition.py` que compone el
registry de tools con los servicios reales (radar, scoring, feedback,
criteria, chat) y el graph v2; lo usan el harness y los tests de integracion
(reemplaza al `build_stack` de conftest donde convenga). `api/` y
`api/dependencies.py` NO se tocan: los contratos HTTP de chat son H4.3
(FR-025).

**Rationale**: H4.1 no dejo root de composicion de produccion (H4.3 lo
compone); el harness necesita un stack real de tools para el E2E.

**Alternatives considered**: ampliar `workers/composition.py`: rechazado —
los workers no ejecutan el runtime conversacional en este incremento.

## R-13 — Suite de abuso determinista como gate (UM-H4-016)

**Decision**: `tests/unit/agent/tools/test_abuse_suite.py` (y casos en
integracion) cubre, SIN LLM: acceso cruzado con ids manipulados en las 8
tools (0 acceso en el 100% de los casos), argumentos fuera de schema
(rechazo tipado, 0 efectos), prompt injection en argumentos/contenido (0
tools no pedidas, 0 datos ajenos), solicitudes de volumen excesivo (redaccion
acota la salida) y mutacion sin confirmacion (apply sin confirmacion/key:
0 efectos). Es parte del harness de cierre (FR-022/FR-023).

**Rationale**: FR-022 exige un gate deterministico e independiente del LLM;
la suite corre contra el executor, no contra el modelo.

**Alternatives considered**: evals con LLM: rechazados — H4.4 (UM-H4-027)
es el dueño de los evals del graph; el gate de abuso debe ser determinista.

## R-14 — Topologia v2 con loop acotado; run_tools registra tool runs

**Decision**: `graph-topology-v2.json` declara los nodos
`start/generate_reply/run_tools/persist_reply` con edge condicional
(`generate_reply → run_tools` si hay `tool_calls`; `run_tools →
generate_reply` mientras queden calls y el contador no supere
`AGENT_TOOLS_MAX_CALLS_PER_TURN`; `generate_reply → persist_reply` si no
hay calls). `run_tools` ejecuta las calls pendientes y registra una fila
`agent_node_runs` por call (`node_kind='tool'`, `source="agent.tool"`); un
fallo de tool queda en `tool_results` con error tipado y NO rompe el turno
(la respuesta puede declarar el fallo; el estado es recuperable, FR-004).

**Rationale**: FR-004 (todo tool run registrado), el seam para H4.3 y el
limite protege presupuestos (H4.4).

**Alternatives considered**: un nodo por tool en el graph: rechazado —
acopla la topologia al catalogo de tools; el registry es el catalogo.
