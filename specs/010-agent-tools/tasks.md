# Tasks: Tools explicitas y permisos

**Input**: Design documents from `specs/010-agent-tools/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice starts
with the failing contract/unit test named here"). En cada fase se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia de `spec.md` conservando
los slices del plan. Setup publica contratos y settings `AGENT_TOOLS_*`;
Foundational publica la capa de datos (migraciÃ³n `0010`, propuestas) y el
nÃºcleo registry/executor; US1 completa la polÃ­tica comÃºn + topology v2 con el
loop de tools; US3 el ciclo de vida de propuestas; US2/US4/US5 las tools de
lectura/explicaciÃ³n; US6/US7 feedback y contexto urbano (P1); US8 + Polish la
suite de abuso, el harness y el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar el tool contract v1, los schemas v2 machine-checkable y
los settings `AGENT_TOOLS_*`/`AGENT_PROPOSAL_TTL_HOURS` que usarÃ¡n todas las
historias.

- [X] T001 [P] Definir el tool contract v1 machine-checkable (registry_version
  `agent-tool-contract-v1`, contract_version 1, las 8 tools con name/
  description/mutating/requires_confirmation/idempotent/timeout_seconds/
  input_schema/output_schema/output_limits con max_items y forbidden_keys)
  en `contracts/agent/tools/tool-contract-v1.json`
- [X] T002 [P] Definir el state schema v2 machine-checkable (schema_version 2,
  fields v1 + tool_calls list y tool_results list con item shapes) en
  `contracts/agent/v2/state-schema-v2.json`
- [X] T003 [P] Definir la graph topology v2 machine-checkable (topology_version
  2, nodes start/generate_reply/run_tools/persist_reply, edges con condition
  tool_calls/loop/no_tool_calls, tools con los 8 nombres, interrupts `[]`) en
  `contracts/agent/v2/graph-topology-v2.json`
- [X] T004 [P] Definir el reply schema v2 machine-checkable (schema_version
  reply-v2, reply_text 1..2000, refs, tool_calls list de `{tool, args}` con
  max_items 5) en `contracts/agent/v2/reply-schema-v2.json`
- [X] T005 [P] AÃ±adir los settings `AGENT_TOOLS_*` y `AGENT_PROPOSAL_TTL_HOURS`
  (`AGENT_TOOLS_STATE_SCHEMA_VERSION` 2, `AGENT_TOOLS_TOPOLOGY_VERSION` 2,
  `AGENT_TOOLS_CONTRACT_VERSION` v1, `AGENT_TOOLS_MAX_CALLS_PER_TURN` 5,
  `AGENT_TOOLS_TIMEOUT_SECONDS` 10, `AGENT_TOOLS_OUTPUT_MAX_ITEMS` 20,
  `AGENT_PROPOSAL_TTL_HOURS` 24) validados al iniciar y registrados en
  `_known_fields` en `src/umbral/infrastructure/config/settings.py` con test
  unit en `tests/unit/config/test_agent_settings.py`

**Checkpoint**: contratos y settings publicados; las historias tienen
versiones y lÃ­mites disponibles.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Capa de datos compartida (migraciÃ³n `0010`, propuestas) y el
nÃºcleo registry/executor de tools con validaciÃ³n comÃºn. Nada de las historias
comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T006 Escribir el test de migraciÃ³n: `0010_agent_tools` aplica y hace
  rollback, crea `search_profile_update_proposals`, el ENUM `proposal_state`,
  el Ã­ndice Ãºnico parcial `uq_proposals_profile_idempotency` y las FK en
  `tests/migrations/test_0010_agent_tools.py`
- [X] T007 [P] Escribir el conformance test del tool contract: carga
  `tool-contract-v1.json`, expone exactamente las 8 tools con flags y que
  output_limits reuse las forbidden_keys del events registry en
  `tests/contract/test_agent_tools_contract.py`

### Implementation for Foundational

- [X] T008 [P] Definir el modelo `SearchProfileUpdateProposalRow` (session_id
  FK, search_profile_id FK, base_profile_version int, diff JSONB, impact
  JSONB, state ENUM `proposal_state`, expires_at, applied_idempotency_key
  nullable, rejection_reason nullable, actor/mixin de auditorÃ­a; Ã­ndice
  parcial `uq_proposals_profile_idempotency`) en
  `src/umbral/infrastructure/db/models/agent.py`
- [X] T009 Escribir la migraciÃ³n `0010_agent_tools` (crea
  `search_profile_update_proposals` con ENUM, Ã­ndice Ãºnico parcial, FKs e
  Ã­ndices) en `alembic/versions/0010_agent_tools.py`
- [X] T010 [P] Implementar el repositorio de propuestas
  (`ProposalRepository`: insert, get scoped por sesiÃ³n/usuario,
  latest_pending_for_profile, update state/rejection/apply key) en
  `src/umbral/infrastructure/db/repositories/agent.py`
- [X] T011 [P] Implementar el contract loader de tools (patrÃ³n registry:
  parsea y valida `tool-contract-v1.json`) en
  `src/umbral/infrastructure/agent/tools/contract_loader.py`
- [X] T012 [P] Definir los contracts del registry/executor (`ToolCall`,
  `ToolResult`, `ToolRunContext`, errores `ToolNotFound`,
  `ToolArgsInvalid`, `ToolScopeViolation`, `ToolConfirmationRequired`,
  `ToolIdempotencyConflict`, `ToolTimeout`) en
  `src/umbral/agent/tools/contracts.py`
- [X] T013 [P] Implementar `agent/tools/registry.py`: carga el contract,
  `get_tool(name)`, `validate_args(tool, args)` contra input_schema y
  `apply_redaction(tool, output)` contra output_limits/forbidden_keys en
  `src/umbral/agent/tools/registry.py`

**Checkpoint**: tabla de propuestas desplegable, contract loader y registry
con validaciÃ³n; las historias construyen sobre esto.

---

## Phase 3: US1 - Contrato y politica comun de tools

**Goal**: UM-H4-007 (FR-001..FR-004): el executor aplica la polÃ­tica comÃºn a
cualquier tool â€” identidad, search scope, schema, timeout, idempotencia,
confirmaciÃ³n y redacciÃ³n â€” y registra cada invocaciÃ³n como tool run.

**Independent Test**: `tests/unit/agent/tools/test_executor.py` invoca una tool
fake con identidad vÃ¡lida, ids ajenos, args fuera de schema, timeout y
volumen excesivo y verifica que la polÃ­tica se cumple en el 100% de los casos.

### Tests for US1

- [X] T014 [P] [US1] Escribir los unit tests del executor: scope check (ids
  ajenos denegados), args fuera de schema (error tipado, 0 efectos),
  redacciÃ³n (forbidden_keys y max_items), timeout, registro de `NodeRun`
  con node_kind='tool' y source agent.tool en
  `tests/unit/agent/tools/test_executor.py`
- [X] T015 [P] [US1] Escribir los conformance tests de los schemas v2:
  state-schema-v2 serializable con tool_calls/tool_results, graph-topology-v2
  igual al builder y tools = 8 nombres, reply-schema-v2 con tool_calls <= 5 en
  `tests/contract/test_agent_state_schema_v2.py`,
  `tests/contract/test_agent_graph_topology_v2.py`,
  `tests/contract/test_agent_reply_schema_v2.py`

### Implementation for US1

- [X] T016 [US1] Implementar `agent/tools/executor.py`: `execute_tool(*,
  user_id, session_id, search_profile_id, tool, args, confirmation,
  idempotency_key)` que valida identidad/scope/schema/confirmation/tiempo,
  delega en la implementaciÃ³n, aplica redacciÃ³n y registra un tool run en
  `src/umbral/agent/tools/executor.py`
- [X] T017 [P] [US1] Implementar el recurso `agent/tools/tools.py` con el stub
  de las 8 implementaciones (delegaciÃ³n a servicios, verificado en fases
  posteriores) en `src/umbral/agent/tools/tools.py`
- [X] T018 [US1] Ampliar `agent/graph.py` con `build_topology_v2`: nodo
  `run_tools` (ejecuta tool_calls pendientes vÃ­a executor, escribe
  tool_results redactados, registra tool runs) y edge condicional con loop
  acotado por `AGENT_TOOLS_MAX_CALLS_PER_TURN`; estado v2 en
  `src/umbral/agent/graph.py` y `src/umbral/agent/state.py`
- [X] T019 [P] [US1] Implementar `infrastructure/agent/composition.py`:
  `build_tool_registry(services)` y `build_agent_stack_v2(...)` con servicios
  reales (radar/scoring/feedback/criteria/chat) para tests/harness en
  `src/umbral/infrastructure/agent/composition.py`

**Checkpoint**: FR-001..FR-004; SC-001. El executor y el loop estÃ¡n probados;
los 8 stubs delegan y se completan por historia.

---

## Phase 4: US3 - Proponer y confirmar cambios de radar

**Goal**: UM-H4-009 y UM-H4-010 (FR-007..FR-012): propuestas durables con
ciclo de vida determinista, diff validado, confirmaciÃ³n explÃ­cita, idempotency
key, obsolescencia y vencimiento.

**Independent Test**: `tests/integration/agent/tools/test_proposal_lifecycle.py`
proposeâ†’confirmâ†’apply versiona el perfil y dispara recomputaciÃ³n; replay con
la misma key no duplica; obsolescencia rechaza con error tipado.

### Tests for US3

- [X] T020 [P] [US3] Escribir los unit tests del servicio de propuestas:
  propose crea pending con base_profile_version, apply valida
  (confirmaciÃ³n/key/estado/vigencia/versiÃ³n base), replay con la misma key,
  rechazo por obsolescencia (ConcurrencyConflict) y expire en
  `tests/unit/application/agent/tools/test_proposals.py`
- [X] T021 [P] [US3] Escribir los tests de integraciÃ³n del ciclo de vida:
  proposeâ†’apply versiona el perfil y dispara run preservando el anterior;
  apply sin confirmaciÃ³n/propuesta ajena/vencida/ya usada â†’ 0 efectos;
  obsolescencia con perfil cambiado â†’ reject con error tipado; replay con la
  misma key â†’ 0 duplicados en
  `tests/integration/agent/tools/test_proposal_lifecycle.py`,
  `tests/integration/agent/tools/test_proposal_obsolescence.py`,
  `tests/integration/agent/tools/test_proposal_replay.py`
- [X] T022 [P] [US3] Escribir el conformance test de eventos: el registry
  acepta `search_profile.update_proposed.v1` y
  `search_profile.update_applied.v1` con sus keys y rechaza tipos
  desconocidos en `tests/contract/test_agent_tool_events.py`
- [X] T023 [P] [US3] Escribir el unit test del duty de vencimiento:
  `expire_search_profile_proposals(ttl_hours)` marca pending expiradas como
  rejected('expired') e idempotente en
  `tests/unit/infrastructure/agent/tools/test_expire.py`

### Implementation for US3

- [X] T024 [US3] Definir contracts/puertos del servicio de propuestas
  (`Proposal`, `ProposalChange`, `AppliedProposal`, errores
  `ProposalNotFound`, `ProposalNotPending`, `ProposalExpired`,
  `ProposalNotConfirmed`, `ProposalStale`, `ProposalIdempotencyMismatch`)
  en `src/umbral/application/agent/tools/contracts.py` y
  `src/umbral/application/agent/tools/ports.py`
- [X] T025 [US3] Implementar `application/agent/tools/proposals.py`: `propose`
  (diff validado contra la polÃ­tica/validation path del radar, impacto, TTL,
  evento `search_profile.update_proposed.v1`), `apply` (validaciones + 
  `RadarService.update_profile(expected_version=base)` + single use +
  idempotency replay + obsolescencia vÃ­a `ConcurrencyConflict` + evento
  `search_profile.update_applied.v1`), `get` scoped, `expire` en
  `src/umbral/application/agent/tools/proposals.py`
- [X] T026 [US3] Implementar la tool `propose_search_profile_update` (delega
  en proposals.propose) en `src/umbral/agent/tools/tools.py`
- [X] T027 [US3] Implementar la tool `apply_search_profile_update` (delega en
  proposals.apply con confirmation + idempotency_key) en
  `src/umbral/agent/tools/tools.py`
- [X] T028 [US3] Implementar `infrastructure/agent/proposals/expire.py` y
  registrar el duty `expire_search_profile_proposals` en
  `workers/scheduler.py` (orden recovery-first, junto a
  `purge_agent_checkpoints`)
- [X] T029 [US3] Actualizar el events registry: tipos aditivos
  `search_profile.update_proposed.v1` y `search_profile.update_applied.v1`
  con sus keys en `contracts/events/v1/events-registry.json`

**Checkpoint**: FR-007..FR-012; SC-003, SC-004.

---

## Phase 5: US2 - Consultar el perfil del radar

**Goal**: UM-H4-008 (FR-005/FR-006): get_search_profile devuelve solo el
perfil autorizado de la sesiÃ³n (snapshot vigente + criterios ejecutables +
estado), 0 acceso cruzado.

**Independent Test**: `tests/unit/agent/tools/test_get_search_profile.py` lee
el perfil desde la sesiÃ³n correcta y desde sesiones ajenas (ids manipulados).

### Tests for US5

- [X] T030 [P] [US2] Escribir los unit tests de get_search_profile: snapshot +
  criterios ejecutables + estado del radar; perfil ajeno denegado en
  `tests/unit/agent/tools/test_get_search_profile.py`

### Implementation for US2

- [X] T031 [US2] Implementar la tool `get_search_profile` (radar get_profile +
  criteria latest_compilation + estado; redacciÃ³n sin geometry/valor) en
  `src/umbral/agent/tools/tools.py`

**Checkpoint**: FR-005/FR-006; SC-002.

---

## Phase 6: US4 - Encontrar y entender matches

**Goal**: UM-H4-011 y UM-H4-012 (FR-013..FR-016): find_matches estrictamente
de solo lectura (items persistidos del Ãºltimo run; estado explÃ­cito sin run o
stale) y explain_match sobre evidencia persistida, 0 afirmaciones no
soportadas.

**Independent Test**: `tests/unit/agent/tools/test_find_matches.py` y
`tests/unit/agent/tools/test_explain_match.py` sobre runs publicados y
radares sin runs.

### Tests for US4

- [X] T032 [P] [US4] Escribir los unit tests de find_matches: items del Ãºltimo
  run publicado con overlay dismissed, estado explÃ­cito (run_id null/stale)
  sin inventar resultados y 0 recomputaciones en
  `tests/unit/agent/tools/test_find_matches.py`
- [X] T033 [P] [US4] Escribir los unit tests de explain_match: recupera la
  explicaciÃ³n persistida (score version, reasons, risks, missing_data,
  evidence_refs), item ajeno denegado, 0 afirmaciones nuevas en
  `tests/unit/agent/tools/test_explain_match.py`

### Implementation for US4

- [X] T034 [US4] Implementar la tool `find_matches` (RadarService.get_matches
  read-only; run_id null + stale cuando no hay run publicado) en
  `src/umbral/agent/tools/tools.py`
- [X] T035 [US4] Implementar la tool `explain_match`
  (ScoringService.get_explanation, declara faltantes) en
  `src/umbral/agent/tools/tools.py`

**Checkpoint**: FR-013..FR-016; SC-005.

---

## Phase 7: US5 - Comparar oportunidades en contexto

**Goal**: UM-H4-013 (FR-017/FR-018): compare_listings valida pertenencia al
radar de la sesiÃ³n y lÃ­mite; usa la comparaciÃ³n estructurada persistida; 0
ganador generativo.

**Independent Test**: `tests/unit/agent/tools/test_compare_listings.py` con
listings del radar, fuera de contexto y mÃ¡s del lÃ­mite.

### Tests for US5

- [X] T036 [P] [US5] Escribir los unit tests de compare_listings: pertenencia y
  lÃ­mite validados, dimensiones/faltantes, listing fuera de contexto
  denegado, 0 ganador generativo en
  `tests/unit/agent/tools/test_compare_listings.py`

### Implementation for US5

- [X] T037 [US5] Implementar la tool `compare_listings`
  (ScoringService.build_comparison con lÃ­mite y scope) en
  `src/umbral/agent/tools/tools.py`

**Checkpoint**: FR-017/FR-018; SC-006.

---

## Phase 8: US6 - Registrar feedback y aprender

**Goal**: UM-H4-014 (FR-019/FR-020): record_feedback idempotente con
like/dislike + reason_keys opcionales; propuesta de aprendizaje cuando
corresponde; tipos fuera de contrato rechazados.

**Independent Test**: `tests/unit/agent/tools/test_record_feedback.py` registra
el mismo feedback dos veces y cambia decisiÃ³n (noop/compensaciÃ³n).

### Tests for US6

- [X] T038 [P] [US6] Escribir los unit tests de record_feedback: evento
  idempotente (repetir â†’ noop), like/dislike con reason_keys, cambio de
  decisiÃ³n con supersede, `save`/`dismiss`/`contacted` rechazados con error
  tipado, learning proposal devuelta en
  `tests/unit/agent/tools/test_record_feedback.py`

### Implementation for US6

- [X] T039 [US6] Implementar la tool `record_feedback`
  (FeedbackService.record_feedback con idempotency_key; resultado con
  learning_proposal_id) en `src/umbral/agent/tools/tools.py`

**Checkpoint**: FR-019/FR-020; SC-007.

---

## Phase 9: US7 - Consultar contexto urbano (P1)

**Goal**: UM-H4-015 (FR-021): search_urban_context consulta solo signals
versionadas y respeta la precisiÃ³n geogrÃ¡fica autorizada; 0 datos inventados.

**Independent Test**: `tests/unit/agent/tools/test_search_urban_context.py` con
zona con y sin signals y precisiÃ³n no autorizada.

### Tests for US7

- [X] T040 [P] [US7] Escribir los unit tests de search_urban_context: solo
  signals versionadas (fuente/fecha/algoritmo), coordenadas omitidas cuando la
  precisiÃ³n no es exact/block, ausencia declarada en
  `tests/unit/agent/tools/test_search_urban_context.py`

### Implementation for US7

- [X] T041 [US7] AÃ±adir el seam de lectura `list_urban_signals(listing_id)` en
  `src/umbral/application/criteria/service.py` (usa el puerto
  `UrbanSignalRepository.list_for_listing`, respeta la polÃ­tica de precisiÃ³n
  `_authorized_geometry`)
- [X] T042 [US7] Implementar la tool `search_urban_context` (delega en
  criteria.list_urban_signals; redacciÃ³n de geometry) en
  `src/umbral/agent/tools/tools.py`

**Checkpoint**: FR-021; SC-008.

---

## Phase 10: US8 - Aislamiento y abuso de tools

**Goal**: UM-H4-016 (FR-022/FR-023): suite determinista que cubre el 100% de
las tools â€” acceso cruzado, args manipulados, prompt injection, outputs
excesivos y mutaciÃ³n sin confirmaciÃ³n â€” como gate del incremento.

**Independent Test**: `tests/unit/agent/tools/test_abuse_suite.py` pasa el
100% de los casos adversarios de forma determinista (0 LLM).

### Tests for US8

- [X] T043 [P] [US8] Escribir la suite de abuso determinista: acceso cruzado
  con ids manipulados en las 8 tools (0 acceso en el 100%), args fuera de
  schema (rechazo tipado, 0 efectos), prompt injection en args (0 tools no
  pedidas, 0 datos ajenos), outputs excesivos (redacciÃ³n acota), mutaciÃ³n sin
  confirmaciÃ³n (0 efectos persistentes) en
  `tests/unit/agent/tools/test_abuse_suite.py`

**Checkpoint**: FR-022/FR-023; SC-009.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Harness `check-agent-tools.ps1` registrado en `check.ps1`,
arquitectura de capas, integraciÃ³n del loop con checkpointer Postgres y cierre
con evidencia.

- [X] T044 [P] Escribir el conformance test del harness: `check-agent-tools.ps1`
  existe, lista los paths obligatorios y falla si falta alguno en
  `tests/contract/test_agent_tools_harness.py`
- [X] T045 [P] Escribir el test de integraciÃ³n del loop de tools con el
  checkpointer Postgres (testcontainers): el turno ejecuta tool_calls
  acotadas, cada call deja una fila `agent_node_runs` node_kind='tool' y un
  fallo de tool no rompe el turno en
  `tests/integration/agent/tools/test_graph_tool_loop.py`
- [X] T046 [P] Escribir el test de aislamiento de tools en integraciÃ³n:
  sesiones/radares ajenos con ids manipulados denegados con Postgres en
  `tests/integration/agent/tools/test_tools_isolation.py`
- [X] T047 Ampliar el test de arquitectura: la capa `agent/tools` solo consume
  puertos de application (0 imports de infraestructura) y 0 superficies
  HTTP/UI nuevas en `tests/architecture/test_agent_boundaries.py`
- [X] T048 Crear `scripts/check-agent-tools.ps1` (paths obligatorios:
  `tests\unit\agent\tools`, `tests\unit\application\agent\tools`,
  `tests\unit\infrastructure\agent\tools`, `tests\unit\config\test_agent_settings.py`,
  `tests\contract\test_agent_tools_contract.py`, `test_agent_state_schema_v2.py`,
  `test_agent_graph_topology_v2.py`, `test_agent_reply_schema_v2.py`,
  `test_agent_tool_events.py`, `test_agent_tools_harness.py`,
  `tests\architecture\test_agent_boundaries.py`, `tests\integration\agent\tools`,
  `tests\migrations\test_0010_agent_tools.py`) y registrarlo en `check.ps1`
  con detecciÃ³n de superficie (`src\umbral\agent\tools` +
  `tests\contract\test_agent_tools_contract.py`)
- [X] T049 Cerrar: correr los 7 escenarios de `quickstart.md` y
  `.\scripts\check.ps1` desde checkout limpio; registrar evidencia en
  `docs/runbooks/evidence/agent-tools-acceptance.md` y marcar UM-H4-007 a
  UM-H4-016 en `docs/product/backlog.md`

**Checkpoint**: FR-024/FR-025; SC-010. Incremento cerrado con evidencia.

---

## Dependencies

- T001..T005 (Setup) â†’ T006..T013 (Foundational) â†’ US1 â†’ US3 â†’ (US2, US4,
  US5, US6, US7 en paralelo sobre los stubs) â†’ US8 â†’ Polish.
- Fases con **historia** dependen de Foundational (T006..T013) y del executor
  (T016).
- US3 depende de US1 solo en el sentido de que la tool `apply` la registra el
  executor; el servicio de propuestas (T024..T025) es independiente y puede
  adelantarse.
- Las herramientas de US2/US4/US5/US6/US7 dependen de T017 (stubs) y de los
  servicios existentes (radar/scoring/feedback/criteria), ya implementados en
  H2/H3.

## Parallel Opportunities

- Setup: T001..T005 (5 tareas paralelas, archivos distintos).
- Foundational: T006/T007 (tests) y T008..T013 (implementaciÃ³n).
- US3 tests: T020..T023 (4 paralelas).
- Tools de lectura: T030, T032, T033, T036, T038, T040 paralelas entre sÃ­
  (archivos de test distintos).
- Polish: T044..T048 paralelas salvo T049 (cierre).

## Implementation Strategy (MVP â†’ full)

- MVP: US1 completo (executor + loop + composition) sobre stubs â†’ un turno
  del graph ejecuta tool_calls y registra tool runs sin persistencia de
  propuestas.
- Siguiente: US3 (ciclo de propuestas con su migraciÃ³n) â€” el slice con
  mayor riesgo de datos.
- Luego: US2/US4/US5/US6/US7 (tools delgadas sobre servicios H2/H3).
- Cierre: US8 (abuse suite) + Polish (harness + arquitectura + evidencia).





