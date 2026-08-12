# Tasks: Criterios suaves activos y chat de preferencias

**Input**: Design documents from `/specs/014-soft-preferences-chat/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks grouped by user story (US1/US2 = Fase 0 + Fase 1 del roadmap, el alcance solicitado; US3/US4 completan el spec).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Foundational — Contratos y vocabulario (bloquea todo)

**Purpose**: el vocabulario canónico de preferencias y su contrato son la base de la traducción determinística (FR-005) y del resto de las historias.

- [X] T001 [P] Crear `specs/014-soft-preferences-chat/contracts/preferences-vocabulary-v1.json` (ya redactado en plan) y publicarlo como `contracts/criteria/v1/preferences-vocabulary-v1.json` en el repo de contratos
- [X] T002 [P] Contract test del vocabulario en `tests/contract/test_preferences_vocabulary.py`: parse estructural, claves únicas, conceptos referenciados existen en `concepts-seed-v1.json`, formato de aliases/polarity/value
- [X] T003 Implementar `src/umbral/application/agent/tools/preferences.py`: módulo puro `PreferenceVocabulary` que carga el contrato y resuelve una frase canónica → `(concept_key, polarity, value)`; errores tipados `PreferenceUnknownConcept` / `PreferenceVocabularyInvalid`
- [X] T004 [P] Unit tests de `preferences.py` en `tests/unit/application/agent/tools/test_preferences.py`: alias exacto, alias con espacios/case, sin match → `PreferenceUnknownConcept`, contrato inválido → error estructural
- [X] T005 [P] Infrastructure loader `src/umbral/infrastructure/agent/tools/preferences_loader.py` (mismo patrón que `contract_loader.py`) con path `contracts/criteria/v1/preferences-vocabulary-v1.json`

**Checkpoint**: vocabulario publicado y traducible por código; base para US1 (seed) y US2 (tool).

---

## Phase 2: User Story 1 - Radar que considera preferencias suaves (P1) 🎯 (Fase 0)

**Goal**: la capa suave activa localmente: concepts + extraction + observaciones sembradas, perfil que compila criterios suaves, runs que los usan y explicaciones que citan evidencia.

**Independent Test**: con `scripts/seed-local.py` corrido, `concepts`/`concept_versions`/`extraction_versions`/`listing_observations` poblados; un perfil con un fact de luminosidad produce un run cuyas explicaciones citan evidencia de observaciones.

### Implementación para User Story 1

- [X] T006 [P] [US1] Unit test del seed extendido en `tests/unit/ops/test_seed_local_soft.py`: idempotencia (2 corridas → mismos counts), observaciones por regla publicadas, cualitativos no fallan el seed si el modelo no responde
- [X] T007 [US1] Extender `scripts/seed-local.py`: sembrar `concepts` + `concept_versions` desde `contracts/criteria/v1/concepts-seed-v1.json` (vía `CriteriaService.seed_registry` o repos existentes) — idempotente
- [X] T008 [US1] Extender `scripts/seed-local.py`: sembrar `extraction_versions` desde `contracts/criteria/v1/extraction-v1.json` y correr `process_extraction` inline (scope full) sobre los listings demo, publicando `listing_observations` (reglas siempre; cualitativos `failed` con código si el modelo no está)
- [X] T009 [US1] Verificar composición del extractor en `src/umbral/infrastructure/criteria/composition.py`: el extractor structured (modelo) está cableado con el gateway de modelo; documentar en research.md el hallazgo si requiere configuración adicional
- [X] T010 [US1] Validar que `compile_profile` incluye facts con cualquier `fact_source` (incluida la futura fuente `chat`) en `src/umbral/application/criteria/service.py` — si hay restricción de fuente, quitarla con test
- [X] T011 [P] [US1] Smoke test de explicaciones: unit/integration que un run con observations activas produce `criterion_evaluations` con `criterion_key` de concepto y `explain_match` devuelve evidencia no vacía en `tests/contract/` (o integration con Postgres si aplica)

**Checkpoint**: US1 funcional — el radar local considera preferencias suaves y explica con evidencia.

---

## Phase 3: User Story 2 - Preferencia suave expresada en el chat (P1) 🎯 (Fase 1)

**Goal**: el chat propone preferencias canónicas con HITL; al confirmar se registra un fact con fuente `chat`, se recompila y se recomputa.

**Independent Test**: "quiero un depto luminoso" → propuesta pending → confirmar → `preference_facts` con `fact_source=chat` y un run nuevo.

### Tests para User Story 2 ⚠️ (escribir y ver fallar antes de implementar)

- [X] T012 [P] [US2] Contract test tool-contract-v2: `propose_search_preference_update` existe con flags (mutating, requiere confirmación vía HITL, idempotente) y schema `{preference: {key, polarity, value?, operation?}}` en `tests/contract/test_agent_tools_contract.py`
- [X] T013 [P] [US2] Contract test intent-schema-v3: `refinamiento` incluye `propose_search_preference_update` en `tests/contract/test_agent_intent_schema_v3.py`
- [X] T014 [P] [US2] Unit test tool: `propose_search_preference_update` crea `LearningProposal` pending con change `preference_fact` (concepto, polaridad, pesos de política) y emite `learning.proposal_created.v1` en `tests/unit/agent/tools/test_propose_preference.py`
- [X] T015 [P] [US2] Graph v3 test: turno con intent `refinamiento` → tool preference → interrupt `proposal_decision` con diff de preferencia → approve → `confirm_proposal` ejecutado (fact + recompute) en `tests/contract/test_agent_graph_topology_v3.py`
- [X] T016 [P] [US2] Evals golden: casos "quiero un depto luminoso" (propose → confirm) y rechazo accionable de concepto no soportado en `contracts/agent-evals/v1/conversations-golden-v1.json` + stub en `src/umbral/infrastructure/agent_evals/composition.py`

### Implementación para User Story 2

- [X] T017 [US2] Agregar `propose_search_preference_update` a `contracts/agent/tools/tool-contract-v2.json` con descripción del vocabulario y errores conocidos (`preference.unknown_concept`)
- [X] T018 [US2] Agregar la tool a `allowed_tools` de `refinamiento` en `contracts/agent/v3/intent-schema-v3.json`
- [X] T019 [US2] Ampliar el intent compiler: parámetro canónico `preferencia` en el schema del prompt y ejemplos ("quiero un depto luminoso" → preferencia=luminoso) en `src/umbral/agent/intent/compiler.py`
- [X] T020 [US2] Implementar el servicio de propuesta: nuevo método en `src/umbral/application/feedback/service.py` (o `src/umbral/application/agent/tools/preference_proposals.py` según research D-02) `propose_preference(...)`: resuelve vocabulario → valida concepto contra catálogo → crea `LearningProposal` pending (weights de `learning-policy-v1.json`, evidence_refs con correlation_id) → emite evento; errores: `PreferenceUnknownConcept`, contradicción con fact vigente (devuelve `impact.contradicts`)
- [X] T021 [US2] Implementar la tool en `src/umbral/agent/tools/tools.py` (`_propose_preference`) delegando al servicio; shape de salida `{proposal_id, diff, impact, state, expires_at}` (igual al de `propose_search_profile_update`)
- [X] T022 [US2] Grafo v3 en `src/umbral/agent/graph.py`: `_waiting_proposal` reconoce la tool de preferencia; `pending_action.kind = preference`; `resolve_decision` con `approve` para preference ejecuta `feedback.confirm_proposal` (o el servicio de preferencias) en vez de `apply_search_profile_update`; `reject` → `feedback.reject_proposal` con nota; `_tool_result_refs` registra `proposal` ref
- [X] T023 [US2] Prompt del grafo: guía de errores `preference.unknown_concept` y `preference.contradiction` (preguntar antes de aplicar) en `src/umbral/agent/graph.py`
- [X] T024 [US2] Web: verificar `apps/web/src/components/chat/proposal-card.tsx` renderiza el diff de preferencia (concepto/polaridad legibles); ajustar tipos en `apps/web/src/lib/chat/types.ts` si el shape del interrupt lo requiere
- [X] T025 [US2] Idempotencia server-side: `_with_idempotency_key` en `src/umbral/agent/graph.py` cubre la tool nueva (derivada de session + concepto + polaridad)

**Checkpoint**: US2 funcional — SC-001/SC-002 verificables en el chat real.

---

## Phase 4: User Story 3 - Revisar y remover preferencias suaves (P2)

**Goal**: el usuario consulta sus preferencias vigentes (fuente, fecha, polaridad) y puede remover una con HITL, dejando trazabilidad.

**Independent Test**: "¿qué preferencias tengo?" lista los facts activos; "saca mi preferencia de luminosidad" propone la remoción y, al confirmar, el fact queda superseded y el run no la considera.

- [X] T026 [P] [US3] Contract test: tool `list_search_preferences` (consulta) y `propose_search_preference_removal` (o `operation: remove` según research D-08) en `tests/contract/test_agent_tools_contract.py`
- [X] T027 [P] [US3] Graph v3 test: remoción con HITL → `remove_preference_fact` (supersede + bump + compile + run) en `tests/contract/test_agent_graph_topology_v3.py`
- [X] T028 [US3] Implementar `list_search_preferences` en `src/umbral/agent/tools/tools.py` + allowed en `consulta` (`intent-schema-v3.json`) — salida: facts activos (concepto, polaridad, fuente, fecha)
- [X] T029 [US3] Implementar remoción: `operation: remove` en el vocabulario/diff, servicio `remove_preference_fact` en `src/umbral/application/feedback/service.py` (mismo patrón que `confirm_proposal` con prior_fact), y branch en `resolve_decision`

**Checkpoint**: US3 funcional — FR-008 completo.

---

## Phase 5: User Story 4 - Contradicción entre preferencias (P3)

**Goal**: el sistema detecta una preferencia opuesta a un fact vigente y pregunta antes de aplicar.

**Independent Test**: con luminosidad negativa vigente, "quiero algo luminoso" devuelve `impact.contradicts` con el fact vigente; al confirmar, el fact previo queda superseded.

- [X] T030 [P] [US4] Unit test: propuesta con polarity opuesta a fact activo → impacto con `contradicts` + fact vigente en `tests/unit/application/agent/tools/test_preferences.py`
- [X] T031 [US4] Implementar detección en el servicio de propuesta (D-08/research) y guía en el prompt del grafo para preguntar antes de aplicar

**Checkpoint**: US4 funcional — FR-009 completo.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: cierre del incremento: harness, evals y documentación.

- [X] T032 [P] Actualizar `scripts/check-agent-tools.ps1` si los contract tests nuevos requieren paths adicionales (test_preferences_vocabulary, test_propose_preference)
- [X] T033 [P] Registrar los casos de preferencia en `contracts/agent-evals/v1/conversations-golden-v1.json` (familia `preferences`) y en `_INTENT_TOOL_BY_FAMILY`/stubs de `src/umbral/infrastructure/agent_evals/composition.py`
- [X] T034 [P] Documentar en `specs/014-soft-preferences-chat/quickstart.md` el resultado de la validación real (counts de tablas, turnos de chat verificados)
- [X] T035 Ejecutar validación completa: `pytest` (unit/contract/architecture), `ruff`, `mypy`, harness `scripts/check.ps1` y `npm run lint/typecheck/test` en `apps/web`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: sin dependencias — vocabulario y traducción pura
- **US1 (Phase 2)**: depende de Phase 1 — desbloquea la capa suave local
- **US2 (Phase 3)**: depende de Phase 1 (vocabulario) y en runtime del seed de US1 (catálogo de conceptos en DB); puede implementarse en paralelo con US1
- **US3 (Phase 4)**: depende de US2 (mismo servicio/flujo HITL)
- **US4 (Phase 5)**: depende de US2 (detección en la propuesta)
- **Polish (Phase 6)**: depende de todas las historias

### Parallel Opportunities

- Phase 1: T001/T002 en paralelo con T004/T005 (contratos vs tests vs loader)
- US1: T006 (test del seed) antes de T007/T008; T009/T010/T011 en paralelo
- US2: T012-T016 (tests) en paralelo entre sí y con T017-T019 (contratos/compiler); T020-T025 secuenciales (servicio → tool → grafo → prompt)
- US3/US4: independientes entre sí una vez US2 termina

## Implementation Strategy

### MVP (Fase 0 + Fase 1 del roadmap = US1 + US2)

1. Phase 1 (vocabulario) → 2. US1 (capa suave local) → 3. US2 (chat de preferencias) → **STOP y VALIDAR** con quickstart (SC-001/SC-002/SC-003)
4. US3 y US4 completan el spec según disponibilidad

### Notas

- Los contract tests del repo (`tests/contract/`) son obligatorios por convención del harness; los unit tests cubren la traducción y el flujo de servicio sin DB.
- Las integraciones con Postgres corren con Docker levantado (convención del repo).
- Commits por grupo lógico de tareas; no commitear sin pedido explícito.
