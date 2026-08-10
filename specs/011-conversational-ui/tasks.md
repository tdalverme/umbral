# Tasks: Comportamiento conversacional y UI

**Input**: Design documents from `specs/011-conversational-ui/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice starts
with the failing contract/unit test named here"). En cada fase se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia de `spec.md` conservando
los slices del plan (Phase A..J). Setup publica contratos v3 + streaming
events y settings `AGENT_CHAT_*`/`AGENT_INTENT_*`/`AGENT_CLARIFICATION_*`/
`AGENT_REPLY_*`; Foundational publica la capa de datos (migraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n `0011`,
idempotencia de envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o) y el runtime v3 reanudable/interruptible; US1/US2
compilaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y aclaraciones; US3 el human-in-the-loop; US4
respuestas grounded; US5 los contratos HTTP de chat streaming; US6/US7/US8 la
UI web (panel, mini-cards, reconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n); US9 la entrada contextual (P1);
Polish la suite de abuso v3, el harness y el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos v3 machine-checkable, el contrato de
streaming events y los settings que usarÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡n todas las historias.

- [X] T001 [P] Definir el state schema v3 machine-checkable (schema_version 3,
  fields v2 + `intent` poblado, `clarification` con pending_params/rounds y
  `pending_action` documentado como `{kind: "proposal", proposal_id}`) en
  `contracts/agent/v3/state-schema-v3.json`
- [X] T002 [P] Definir la graph topology v3 machine-checkable (topology_version
  3, nodos start/compile_intent/clarify/generate_reply/run_tools/
  require_confirmation/resolve_decision/persist_reply, edges condicionales,
  tools con los 8 nombres, `interrupts: ["proposal_decision"]`) en
  `contracts/agent/v3/graph-topology-v3.json`
- [X] T003 [P] Definir el reply schema v3 machine-checkable (schema_version
  reply-v3, reply_text 1..2000, `refs` con entity en {listing, criterion,
  evidence_ref, proposal} y max_items 10, tool_calls max 5) en
  `contracts/agent/v3/reply-schema-v3.json`
- [X] T004 [P] Definir el intent schema v3 machine-checkable (5 intents
  consulta/refinamiento/comparacion/feedback/fuera_de_alcance, parameters[]
  con key/value/confidence, high_impact_missing[], contradictions[] y
  `allowed_tools` por intent) en `contracts/agent/v3/intent-schema-v3.json`
- [X] T005 [P] Definir el contrato de streaming events v1 (7 tipos:
  chat.run_started, chat.reply_fragment, chat.tool_activity,
  chat.interrupt_waiting, chat.run_completed, chat.run_failed,
  chat.run_interrupted, con payloads) en `contracts/chat/v1/streaming-events-v1.json`
- [X] T006 [P] AÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±adir los settings `AGENT_CHAT_STATE_SCHEMA_VERSION` (3),
  `AGENT_CHAT_TOPOLOGY_VERSION` (3), `AGENT_INTENT_SCHEMA_VERSION` (intent-v3),
  `AGENT_INTENT_PROMPT_VERSION` (agent-intent-v1), `AGENT_REPLY_PROMPT_VERSION`
  (agent-reply-v2), `AGENT_CLARIFICATION_MIN_CONFIDENCE` (0.6),
  `AGENT_CLARIFICATION_MAX_ROUNDS` (2), `AGENT_REPLY_MAX_REFS` (10),
  `AGENT_REPLY_CHUNK_WORDS` (8) validados al iniciar y registrados en
  `_known_fields` en `src/umbral/infrastructure/config/settings.py` con test
  unit en `tests/unit/config/test_agent_settings.py`

**Checkpoint**: contratos y settings publicados; las historias tienen
versiones, lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­mites y polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica disponibles.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Capa de datos compartida (migraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n `0011`, idempotencia de
envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o) y el runtime v3 reanudable/interruptible. Nada de las historias
comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T007 Escribir el test de migraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: `0011_chat_streaming` aplica y hace
  rollback, altera `chat_messages` (+ client_message_id, ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ndice ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºnico parcial
  `uq_chat_messages_session_client`) y `search_profile_update_proposals`
  (+ rejection_note, superseded_by_proposal_id, ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ndice
  `ix_proposals_superseded_by`) en `tests/migrations/test_0011_chat_streaming.py`
- [X] T008 [P] Escribir los unit tests del runtime v3: detecciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de
  `__interrupt__` durante el stream, emisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de `InterruptWaiting`, resume con
  `Command(resume=decision)` que reanuda el mismo run sin repetir efectos
  (claim por sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n) en `tests/unit/agent/test_runtime_v3.py`
- [X] T009 [P] Escribir los unit tests del servicio de chat: idempotencia de
  envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o con `client_message_id` (replay ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ mensaje registrado, 0 duplicados) y
  `list_sessions(profile_id)` en `tests/unit/application/chat/test_message_idempotency.py`

### Implementation for Foundational

- [X] T010 [P] Definir los modelos: `chat_messages.client_message_id` (UUID
  nullable + ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ndice ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºnico parcial) en
  `src/umbral/infrastructure/db/models/chat.py` y
  `search_profile_update_proposals.rejection_note` +
  `superseded_by_proposal_id` (FK self, nullable) en
  `src/umbral/infrastructure/db/models/agent.py`
- [X] T011 Escribir la migraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n `0011_chat_streaming` (ALTER de las dos
  tablas con las columnas, ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­ndices y, si la columna estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ restringida, el
  dominio extendido de `rejection_reason`; downgrade completo) en
  `alembic/versions/0011_chat_streaming.py`
- [X] T012 [P] Implementar `ChatService.append_user_message(..., client_message_id)`
  idempotente (replay devuelve el mensaje registrado) y
  `ChatService.list_sessions(search_profile_id)` en
  `src/umbral/application/chat/service.py` y sus puertos en
  `src/umbral/application/chat/ports.py`
- [X] T013 [P] Implementar el runtime v3: detecciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de `__interrupt__` en el
  stream, evento `InterruptWaiting`, parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metro `decision` en `run_turn` y
  resume con `Command(resume=...)` en `src/umbral/agent/runtime.py` y
  `src/umbral/agent/events.py`

**Checkpoint**: capa de datos desplegable y runtime reanudable/interruptible;
las historias construyen sobre esto.

---

## Phase 3: US1 - Compilar intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n a acciones permitidas

**Goal**: UM-H4-017 (FR-001..FR-005): el graph clasifica cada mensaje en
exactamente una intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n del conjunto permitido, la polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica intentÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢tools se
aplica de forma determinista (0 SQL, 0 ranking, 0 mutaciones fuera de
polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica) y la creaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de bÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºsquedas desde el chat queda fuera de alcance
(Q1: dirige al onboarding estructurado).

**Independent Test**: `tests/unit/agent/intent/test_policy.py` envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a mensajes
de cada intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y tool_calls fuera de `allowed_tools` y verifica que la
violaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n se rechaza con error tipado y 0 efectos.

### Tests for US1

- [X] T014 [P] [US1] Escribir el conformance test del intent schema: las 5
  intenciones con sus `allowed_tools` y los parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metros de alto impacto
  (budget/zona/hard_filters/radio) declarados en
  `tests/contract/test_agent_intent_schema_v3.py`
- [X] T015 [P] [US1] Escribir los unit tests del compiler: clasificaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n en
  exactamente una intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metros con confianza, fuera de alcance
  (incluida la creaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de un radar) en `tests/unit/agent/intent/test_compiler.py`
- [X] T016 [P] [US1] Escribir los unit tests de la polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica: `tool_calls`
  fuera de `allowed_tools` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ error tipado, 0 ejecuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y 0 efectos en
  `tests/unit/agent/intent/test_policy.py`
- [X] T017 [P] [US1] Escribir los conformance tests de los schemas v3:
  state-schema-v3 serializable con intent/clarification/pending_action,
  graph-topology-v3 con nodos compile_intent/clarify y
  `interrupts: ["proposal_decision"]`, reply-schema-v3 con refs ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°Ãƒâ€šÃ‚Â¤ 10 en
  `tests/contract/test_agent_state_schema_v3.py`,
  `tests/contract/test_agent_graph_topology_v3.py`,
  `tests/contract/test_agent_reply_schema_v3.py`

### Implementation for US1

- [X] T018 [US1] Implementar `agent/intent/compiler.py`: salida estructurada
  vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a `gateway.generate_structured` con `intent-schema-v3` y prompt
  `agent-intent-v1`; registra la clasificaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n con versiones en
  `src/umbral/agent/intent/compiler.py`
- [X] T019 [P] [US1] Implementar `agent/intent/policy.py`: `validate_tool_calls`
  contra `allowed_tools` de la intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n compilada en
  `src/umbral/agent/intent/policy.py`
- [X] T020 [US1] Ampliar `agent/graph.py` con `build_topology_v3`: nodo
  `compile_intent` al inicio y validaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n determinista de `tool_calls` contra
  la polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica en `run_tools`; estado v3 en `src/umbral/agent/graph.py` y
  `src/umbral/agent/state.py`

**Checkpoint**: FR-001..FR-005; SC-001.

---

## Phase 4: US2 - Aclaraciones de alto impacto

**Goal**: UM-H4-018 (FR-006..FR-010): parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metros de alto impacto ambiguos,
ausentes o contradictorios con el perfil interrumpen con preguntas acotadas
de templates deterministas; rounds acotados; decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n registrada por turno.

**Independent Test**: `tests/unit/agent/intent/test_clarification.py` invoca
el plan de aclaraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n con parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metros de alta confianza, baja confianza,
ausentes y contradictorios y verifica que solo los de alto impacto ambiguos
disparan pregunta (0 adivinanzas).

### Tests for US2

- [X] T021 [P] [US2] Escribir los unit tests de clarificaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: disparo por
  confianza < `AGENT_CLARIFICATION_MIN_CONFIDENCE`, por ausencia necesaria y
  por contradicciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n con el snapshot del perfil; rounds ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°Ãƒâ€šÃ‚Â¤
  `AGENT_CLARIFICATION_MAX_ROUNDS`; templates deterministas; agotados ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢
  imposibilidad + UI estructurada en
  `tests/unit/agent/intent/test_clarification.py`

### Implementation for US2

- [X] T022 [US2] Implementar `agent/intent/clarification.py` (disparo por
  polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica + templates deterministas por parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metro) y el nodo `clarify` en el
  graph v3 (estado `clarification` con pending_params/rounds; la respuesta se
  integra en el siguiente turno) en `src/umbral/agent/intent/clarification.py`
  y `src/umbral/agent/graph.py`

**Checkpoint**: FR-006..FR-010; SC-002.

---

## Phase 5: US3 - Human-in-the-loop: aprobar, editar o rechazar

**Goal**: UM-H4-019 (FR-011..FR-016): toda propuesta se pausa en el checkpoint
(interrupt), la decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n reanuda el MISMO run sin repetir efectos, y las
transiciones interactivas sobre la propuesta durable (rechazo `user` con nota,
ediciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n como propuesta derivada con cadena `superseded_by`, Q2) quedan
auditadas.

**Independent Test**: `tests/integration/chat/test_hitl_lifecycle.py` ejecuta
propose ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ interrupt_waiting ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ approve/reject/edit ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ resume y verifica 0
repeticiones de efectos y estados auditados en la propuesta.

### Tests for US3

- [X] T023 [P] [US3] Escribir los unit tests de las transiciones interactivas:
  reject('user') con nota, derive (original ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ rejected('edited') +
  superseded_by_proposal_id, derivada pending con evento update_proposed),
  0 mutaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de la original, list y waiting_run en
  `tests/unit/application/agent/tools/test_proposal_transitions.py`
- [X] T024 [P] [US3] Escribir los tests de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n del ciclo HITL:
  propose ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ interrupt ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ approve (aplica con confirmaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n + idempotency key,
  versiona perfil y dispara recomputaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n preservando el run anterior) /
  reject / edit (re-interrupt sobre la derivada); decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n sin interrupt ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢
  `agent.no_pending_interrupt`; propuesta distinta a la esperada ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢
  `agent.decision_mismatch`; 0 efectos en todos los rechazos en
  `tests/integration/chat/test_hitl_lifecycle.py`
- [X] T025 [P] [US3] Escribir los tests de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de la cadena de ediciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n:
  la derivada nace pending, la original queda rejected('edited') con el link
  superseded, el replay con la misma idempotency key no duplica y la derivada
  vencida queda rechazada por el duty existente en
  `tests/integration/chat/test_edit_chain.py`

### Implementation for US3

- [X] T026 [US3] Implementar en el servicio de propuestas: `reject(proposal_id,
  reason='user', note)`, `derive(proposal_id, change)` (propuesta nueva
  derivada validada por el camino de `RadarService`, evento
  `search_profile.update_proposed.v1`), `list(profile_id, state)` y
  `waiting_run(proposal_id)`; extender `ProposalRejectionReason` con
  `user`/`edited` en `src/umbral/application/agent/tools/proposals.py`,
  `contracts.py` y `ports.py`
- [X] T027 [US3] Implementar los nodos `require_confirmation` (escribe
  `pending_action = {kind: "proposal", proposal_id}` e interrumpe con payload
  `{type: "proposal_decision", ...}`) y `resolve_decision` (valida
  pending_action contra la decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, delega approve/reject/edit, re-interrumpe
  en edit) en `src/umbral/agent/graph.py`
- [X] T028 [US3] Conectar la resoluciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de decisiones al runtime: el endpoint
  (US5) reanuda con `Command(resume=decision)`; verificar que el claim por
  sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y el ledger de H4.1 impiden efectos duplicados en
  `src/umbral/agent/runtime.py` y su test de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n

**Checkpoint**: FR-011..FR-016; SC-003.

---

## Phase 6: US4 - Respuestas grounded

**Goal**: UM-H4-020 (FR-017..FR-020): el 100% de las afirmaciones cita
objetos persistentes y verificables; refs validadas contra el search scope al
persistir; evidencia faltante declarada (0 hechos completados).

**Independent Test**: `tests/unit/agent/test_grounding.py` persiste replies con
refs vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡lidas, ajenas y no resolubles y verifica validaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, reintento acotado
y declaraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de faltantes.

### Tests for US4

- [X] T029 [P] [US4] Escribir los unit tests de validaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de refs: ref
  resuelta en scope (listing/criterion/evidence_ref/proposal), ref ajena o
  rota ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ reintento acotado y, si persiste, persistencia declarando evidencia
  faltante; refs > `AGENT_REPLY_MAX_REFS` rechazadas en
  `tests/unit/agent/test_grounding.py`

### Implementation for US4

- [X] T030 [US4] Implementar la validaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de refs en `persist_reply` v3:
  resolver cada ref contra el search scope de la sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, reintento acotado,
  declaraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de faltantes y cap `AGENT_REPLY_MAX_REFS`; prompt grounded
  `agent-reply-v2` en `src/umbral/agent/graph.py` y
  `src/umbral/application/chat/service.py` (si la validaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n requiere el
  port de scope)

**Checkpoint**: FR-017..FR-020; SC-004.

---

## Phase 7: US5 - Contratos de chat streaming

**Goal**: UM-H4-021 (FR-021..FR-025): contratos tipados y versionados para
crear sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, enviar mensaje (SSE), reanudar, decidir y recuperar historial;
errores y permisos tipados; reenvÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o sin duplicados; OpenAPI regenerado.

**Independent Test**: `tests/integration/chat/test_streaming_router.py` y
`tests/contract/test_chat_http_contract.py` ejercitan cada operaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n del
contrato con usuarios autorizados, ids manipulados y reintentos.

### Tests for US5

- [X] T031 [P] [US5] Escribir el conformance test del streaming events: el
  contrato expone los 7 tipos con sus payloads y los rechaza/valida en
  `tests/contract/test_chat_streaming_contract.py`
- [X] T032 [P] [US5] Escribir el contract test del HTTP de chat: paths,
  request/response, errores tipados (`chat.*`/`agent.*`) y acciones
  `product.chat.*` en `tests/contract/test_chat_http_contract.py`
- [X] T033 [P] [US5] Escribir los tests de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n del router streaming:
  SSE sobre TestClient con eventos distinguibles (run_started, reply_fragment,
  tool_activity, interrupt_waiting, run_completed/failed), sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
  pausada/archivada y ejecuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n en curso rechazadas con estado tipado en
  `tests/integration/chat/test_streaming_router.py`
- [ ] T034 [P] [US5] Escribir los tests de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n del replay de envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o:
  reintento con el mismo `client_message_id` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ 0 mensajes duplicados y 0 runs
  nuevos en `tests/integration/chat/test_send_replay.py`

### Implementation for US5

- [X] T035 [US5] AÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±adir las acciones de acceso `product.chat.session.create/
  read`, `product.chat.message.write`, `product.chat.decision.write` en
  `src/umbral/domain/identity/policy.py`
- [X] T036 [US5] Implementar `api/routers/chat.py`: POST/GET sessions,
  GET session, GET messages (cursor `before_message_id`), POST messages (SSE),
  POST resume (SSE), POST runs/{run_id}/decision (SSE) y el listado de
  update-proposals; traducciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de ChatError/AgentError con `_problem_for`;
  registro del router en `src/umbral/api/main.py`
- [X] T037 [P] [US5] Re-exportar el OpenAPI (`scripts/export-openapi.ps1`),
  regenerar el cliente web (`npm --workspace @umbral/web run api:generate`) y
  verificar 0 drift con `npm --workspace @umbral/web run api:check` en
  `contracts/openapi/v1/openapi.json`

**Checkpoint**: FR-021..FR-025; SC-005.

---

## Phase 8: US6 - Chat contextual accesible

**Goal**: UM-H4-022 (FR-026..FR-030): panel ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºnico integrado en la pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡gina del
radar (Q3: reanuda la ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºltima sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n o crea, conversaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n nueva desde el panel,
0 rutas dedicadas), streaming con estados, retry, jump-to-latest, teclado y
lectores de pantalla; solo contenido permitido.

**Independent Test**: vitest de componentes (composer, message-list,
stream-status) opera el chat por teclado y roles/live regions y verifica 0
acciones solo con mouse.

### Tests for US6

- [X] T038 [P] [US6] Escribir el vitest del composer: Enter envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a, Shift+Enter
  nueva lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­nea, deshabilitado durante ejecuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n/espera de decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, aria-label
  y errores en `apps/web/src/components/chat/composer.test.tsx`
- [X] T039 [P] [US6] Escribir el vitest del message-list: scroller con
  jump-to-latest, paginaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n hacia atrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s y auto-scroll con override del
  usuario en `apps/web/src/components/chat/message-list.test.tsx`
- [X] T040 [P] [US6] Escribir el vitest del stream-status: estados
  (enviando/ejecutando/esperando confirmaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n/reanudando/fallo/completado)
  con live region y sin dependencia solo de color en
  `apps/web/src/components/chat/stream-status.test.tsx`

### Implementation for US6

- [X] T041 [US6] Implementar `lib/chat/client.ts` (chatApi: sessions, history,
  send, resume, decision) y `lib/chat/use-chat-stream.ts` (hook de estado con
  parsing SSE, dedupe por event id y reconnection) en `apps/web/src/lib/chat/`
- [X] T042 [US6] Implementar los componentes `ChatPanel`, `MessageList`,
  `MessageItem`/`Bubble`, `Composer` y `StreamStatus` en
  `apps/web/src/components/chat/` (roles, live regions, foco, contenido
  permitido)
- [X] T043 [US6] Implementar los route handlers BFF
  `src/app/api/radar/chat/**/route.ts` (sessions, messages GET/POST,
  resume, decision) y el helper `forwardStream` (SSE pipe sin buffer) en
  `apps/web/src/lib/radar/server.ts`
- [X] T044 [US6] Integrar `ChatPanel` como panel ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºnico en la pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡gina
  `apps/web/src/app/(protected)/radar/[id]/page.tsx` (al abrir: reanuda la
  ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºltima sesiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n activa del radar o crea una; acciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n "conversaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n nueva" desde
  el mismo panel)

**Checkpoint**: FR-026..FR-030; SC-006.

---

## Phase 9: US7 - Acciones y mini-cards persistentes

**Goal**: UM-H4-023 (FR-031..FR-034): listings citados como mini-cards
navegables, cambios de perfil con diff y confirmaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, propuestas pendientes
visibles/accionables en la UI estructurada (banner) y el chat con el mismo
estado; 0 objetos que viven solo en el chat.

**Independent Test**: `tests/integration/chat/test_update_proposals_list.py` +
vitest de mini-card/proposal-card verifican que el 100% de los refs renderiza
tarjeta navegable y que las decisiones usan el mismo surface.

### Tests for US7

- [X] T045 [P] [US7] Escribir el vitest del mini-card: listing ref ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ enlace al
  radar/detalle con datos esenciales redactados en
  `apps/web/src/components/chat/mini-card.test.tsx`
- [X] T046 [P] [US7] Escribir el vitest del proposal-card: diff, acciones
  aprobar/editar/rechazar ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ endpoint de decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n con idempotency key en
  `apps/web/src/components/chat/proposal-card.test.tsx`
- [ ] T047 [P] [US7] Escribir el test de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n del listado de
  update-proposals: estado + session_id + waiting_run_id +
  superseded_by_proposal_id; propuestas ajenas denegadas en
  `tests/integration/chat/test_update_proposals_list.py`

### Implementation for US7

- [X] T048 [US7] Implementar `SearchProfileUpdateProposals.list(profile_id,
  state, scope)` y `waiting_run(proposal_id)` en
  `src/umbral/application/agent/tools/proposals.py` y `ports.py`
- [X] T049 [US7] Exponer `GET /api/v1/search-profiles/{search_profile_id}/
  update-proposals?state=` (lista con session_id/waiting_run_id/
  superseded_by_proposal_id) en `src/umbral/api/routers/search_profiles.py`
- [X] T050 [US7] Implementar `MiniCard` y `ProposalCard` en
  `apps/web/src/components/chat/` y el renderizado de refs como tarjetas en
  `MessageItem`
- [X] T051 [US7] Ampliar `ProposalBanner` para propuestas de cambio de agente
  (mismo estado, diff y acciones usando el MISMO endpoint de decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de
  chat) en `apps/web/src/components/radar/proposal-banner.tsx`

**Checkpoint**: FR-031..FR-034; SC-007.

---

## Phase 10: US8 - ReconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n, interrupciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y error parcial

**Goal**: UM-H4-024 (FR-035..FR-038, FR-043): el usuario distingue siempre el
estado del graph (espera/reanudando/fallo/en curso), reanuda sin duplicados y
0 fragmentos parciales como respuesta final; se mide primer fragmento y
errores de streaming.

**Independent Test**: `tests/unit/agent` (hook con fake stream) + integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
de resume verifican estados claros, reanudaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n sin duplicados y 0 partials.

### Tests for US8

- [X] T052 [P] [US8] Escribir el test del hook `use-chat-stream`: dedupe por
  event id, reconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n con `Last-Event-ID` + `POST /resume`, estados del
  turno y retry idempotente en
  `apps/web/src/lib/chat/use-chat-stream.test.ts`
- [ ] T053 [P] [US8] Escribir el test de integraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de reconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: una
  desconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n durante la generaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ resume re-claima el ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºltimo run
  interrumpido y re-emite los eventos restantes; 0 mensajes parciales
  persistidos en `tests/integration/chat/test_resume_reconnect.py`

### Implementation for US8

- [X] T054 [US8] Implementar la reconexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n y el flujo de resume en
  `use-chat-stream` (SSE reconnect con `Last-Event-ID`, llamada a `POST
  /resume` al agotar la conexiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n) en `apps/web/src/lib/chat/use-chat-stream.ts`
- [ ] T055 [US8] Implementar los estados visibles, el retry idempotente
  (mismo `client_message_id`) y el manejo de ejecuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n en curso en otra
  pestaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â±a (`chat.execution_in_progress` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ seguir la misma ejecuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n o
  esperar) en `apps/web/src/components/chat/`
- [X] T056 [P] [US8] Implementar la telemetrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a `chat.first_fragment_ms` y
  `chat.stream_error` con campos seguros vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­a
  `apps/web/src/lib/observability/telemetry.ts` (FR-043)

**Checkpoint**: FR-035..FR-038, FR-043; SC-008.

---

## Phase 11: US9 - Entrada contextual en detalle/comparador (P1)

**Goal**: UM-H4-025 (FR-039/FR-040): preguntas sobre un listing o una
comparaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n conservan el search profile y acotan el scope de evidencia; las
citas retornan al contexto correcto.

**Independent Test**: tests de contenido (context) y vitest de las entradas
verifican scope conservado y enlaces al contexto correcto.

### Tests for US9

- [X] T057 [P] [US9] Escribir los unit tests del contrato de contenido:
  `validate_message_content` acepta `context: {entity, id}` acotado y rechaza
  context malformado o ajeno al radar en
  `tests/unit/application/chat/test_message_context.py`
- [ ] T058 [P] [US9] Escribir los vitest de las entradas contextuales:
  desde detalle y comparador se abre el panel con scope al objeto en
  `apps/web/src/components/chat/contextual-entry.test.tsx`

### Implementation for US9

- [X] T059 [US9] Soportar `context {entity, id}` en el contenido del mensaje
  de usuario (application/chat) y pasarlo al runtime para acotar el scope de
  evidencia del turno (las tools siguen validadas por pertenencia al radar) en
  `src/umbral/application/chat/contracts.py`, `service.py` y
  `src/umbral/agent/state.py`
- [X] T060 [US9] Implementar las entradas contextuales en
  `apps/web/src/app/(protected)/listings/[id]/page.tsx` y
  `apps/web/src/app/(protected)/radar/[id]/compare/page.tsx` (abren/reanudan
  el panel con contexto; las citas retornan al detalle/comparador)

**Checkpoint**: FR-039/FR-040; SC-009.

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Suite de abuso v3 determinista (gate), composiciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de producciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
E2E, arquitectura de capas, harness `check-chat.ps1` registrado en `check.ps1`
y cierre con evidencia.

- [X] T061 [P] Escribir la suite de abuso v3 determinista: violaciones de la
  polÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­tica de intenciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n (0 ejecuciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n), bypass de aclaraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n (0 propuestas),
  abuso de decisiones (run/propuesta ajena, decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n sin interrupt ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ 0
  efectos), replay de envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o (0 duplicados) y acceso cruzado en endpoints de
  chat con ids manipulados (denegado en el 100%) en
  `tests/unit/agent/test_abuse_suite_v3.py`
- [X] T062 [P] Escribir el test E2E de composiciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de producciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n: la app real
  (TestClient) con testcontainers + fake gateway recorre send ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ stream ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢
  propose ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ interrupt_waiting ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ decision approve ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ apply ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ recomputaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
  preservando el run anterior en `tests/integration/api/test_chat_e2e.py`
- [X] T063 [P] Ampliar el test de arquitectura: la capa v3 del agente y el
  router de chat consumen solo puertos de application (0 imports de
  infraestructura/langgraph/FastAPI en domain) en
  `tests/architecture/test_agent_boundaries.py`
- [X] T064 Crear `scripts/check-chat.ps1` (paths obligatorios: contract v3 +
  streaming + http, unit agent/intent + runtime_v3 + abuse_suite_v3,
  application tools/chat, integration chat + api E2E, migrations 0011,
  architecture, config) y registrarlo en `check.ps1` con detecciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n de
  superficie (`src\umbral\api\routers\chat.py` +
  `tests\contract\test_chat_streaming_contract.py`)
- [ ] T065 Cerrar: correr los 9 escenarios de `quickstart.md` y
  `.\scripts\check.ps1` desde checkout limpio (incluye `check-web.ps1` y
  `api:check`); registrar evidencia en
  `docs/runbooks/evidence/conversational-ui-acceptance.md` y marcar UM-H4-017
  a UM-H4-025 en `docs/product/backlog.md`

**Checkpoint**: FR-041..FR-043; SC-010. Incremento cerrado con evidencia.

---

## Dependencies

- T001..T006 (Setup) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ T007..T013 (Foundational) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ US1 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ US2 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ US3 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ (US4,
  US5 en paralelo sobre runtime v3) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ US6 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ (US7, US8, US9 en paralelo sobre
  el panel y el router) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ Polish.
- Fases con **historia** dependen de Foundational (T007..T013): la migraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n
  `0011`, la idempotencia de envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o y el runtime v3 interruptible son
  prerrequisitos bloqueantes.
- US2 depende de US1 (la compilaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n produce los parÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡metros que la
  aclaraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n evalÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âºa); US3 depende del runtime v3 (T013) y del servicio de
  propuestas (T026); US4 depende del graph v3 (T020).
- US5 depende de US3 en el sentido de que el endpoint de decisiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n reanuda el
  interrupt (T027/T028); la idempotencia de envÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­o (T012) ya estÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡ en
  Foundational y puede adelantarse.
- US6/US7/US8/US9 dependen de US5 (contratos HTTP + cliente regenerado) y
  del panel (T044); US7 ademÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¡s de T048/T049 (listado de update-proposals).
- Polish depende de todas las historias; T061 (abuso v3) depende de
  US1/US2/US3/US5 (las superficies que prueba).

## Parallel Opportunities

- Setup: T001..T006 (6 tareas paralelas, archivos distintos).
- Foundational: T007/T008/T009 (tests) y T010..T013 (implementaciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n).
- US1: T014..T017 (4 tests paralelos) y T018/T019/T020.
- US3: T023..T025 (3 tests paralelos) y T026/T027/T028.
- Tras US3: US4 (T029/T030) y US5 (T031..T037) en paralelo; US6 y US5
  comparten el cliente regenerado (T037 antes de T041).
- Tras US6: US7 (T045..T051), US8 (T052..T056) y US9 (T057..T060) en
  paralelo (archivos distintos).
- Polish: T061..T064 paralelas salvo T065 (cierre).

## Implementation Strategy (MVP ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ full)

- MVP: US1 + US2 completos sobre el runtime v3 (intent + aclaraciones) con
  respuestas grounded mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â­nimas ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ un turno del graph clasifica, aclara y
  responde sin HITL.
- Siguiente: US3 (HITL + transiciones de propuestas + migraciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n 0011) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â el
  slice con mayor riesgo de datos y de runtime.
- Luego: US5 (contratos HTTP de streaming) y US4 (grounded) en paralelo.
- DespuÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s: US6 (panel web) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ US7/US8/US9 sobre el panel y el router.
- Cierre: Polish (abuso v3 + E2E composiciÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â³n + harness + evidencia).
