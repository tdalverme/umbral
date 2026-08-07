# Tasks: Feedback y aprendizaje controlado

**Input**: Design documents from `specs/007-feedback-learning/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice starts
with the failing contract/unit/integration test named here"). En cada fase se
escriben primero los tests indicados y se confirma que fallan por la conducta
ausente antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido
(contratos `feedback/v1` y `learning/v1`, 9 eventos aditivos, dominio puro:
reasons, policy, state, signals; puertos, persistencia, migración `0008`,
seams de `RadarService`, settings). US1 entrega el registro inmutable e
idempotente de feedback con acciones en card/detalle; US2 shortlist y
descartados; US3 propuestas de aprendizaje; US4 confirmar/deshacer/ampliar;
US5 el recalculado tras cambios; US6 el feedback libre (P1); US7 el historial
de precio y cambios (P1).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos machine-checkable de feedback y learning,
el registry de eventos ampliado, el conjunto golden y los límites de
arquitectura que usarán todas las historias.

- [X] T001 Definir el contrato de feedback machine-checkable (shape del
  feedback event: event_type/actor/context/reasons/free_feedback/
  idempotency_key; estados de decisión, reglas de supersede/no-op/terminal y
  reglas de los endpoints) en `contracts/feedback/v1/feedback-events.json`
- [X] T002 [P] Definir el seed de quick reasons machine-checkable
  (contract_version, registry_version, reasons con key/label/polarity/
  concept_key/allowed_on) en
  `contracts/feedback/v1/quick-reasons-v1.json`
- [X] T003 [P] Definir el contrato de learning policy machine-checkable
  (min_signals, window_days, min_signal_confidence, cooldown_days,
  proposal_expiration_days, default_suggested_weight,
  default_suggested_confidence y seed v1 `learning-v1`) en
  `contracts/learning/v1/learning-policy-v1.json`
- [X] T004 [P] Ampliar el registry cerrado de eventos con los 9 tipos
  `feedback.*`/`learning.*` (`feedback.recorded.v1`, `learning.proposal_created.v1`,
  `learning.proposal_confirmed.v1`, `learning.proposal_rejected.v1`,
  `learning.proposal_expanded.v1`, `learning.proposal_undone.v1`,
  `learning.proposal_expired.v1` serverside; `feedback.shortlist_viewed.v1`,
  `feedback.dismissed_viewed.v1` clientside; payloads sólo ids/estado/conteos;
  forbidden: texto de feedback libre, razones, evidencia) en
  `contracts/events/v1/events-registry.json`
- [X] T005 [P] Crear el conjunto golden de feedback/learning (seeds de quick
  reasons válidos e inválidos; policies de learning válidas e inválidas;
  cadenas de feedback like→dislike→like con estados esperados; secuencias de
  señales suficientes/insuficientes/contradictorias; lifecycles de propuesta)
  en `tests/fixtures/feedback/quick-reasons-golden.json`,
  `tests/fixtures/feedback/learning-policy-golden.json`,
  `tests/fixtures/feedback/signals-golden.json` y
  `tests/fixtures/feedback/state-golden.json` (reusando fixtures de 005/006)
- [X] T006 [P] Añadir fixtures de arquitectura para los límites de
  `application/feedback` (permite application→domain y adapters→application;
  prohíbe domain→infrastructure, feedback→FastAPI/web/LLM directo, y signals
  con imports de I/O) en `tests/architecture/test_feedback_boundaries.py`

**Checkpoint**: contratos publicados, registry ampliado, conjunto golden
disponible y límites nuevos verificados desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Dominio puro (reasons, learning policy, state machine, signals),
puertos, persistencia, migración `0008`, loaders, settings y los seams nuevos
de `RadarService`. Nada de las historias comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T007 Escribir la conformance de quick reasons: parse/validación (keys,
  polaridad, `allowed_on`, `concept_key` opcional contra el concept registry)
  y seed `quick-reasons-v1` cargable en `tests/contract/test_quick_reasons.py`
- [X] T008 [P] Escribir la conformance de learning policy: parse/validación
  (umbrales numéricos, cooldown/expiración consistentes) y seed `learning-v1`
  cargable en `tests/contract/test_learning_policy.py`
- [X] T009 [P] Ampliar la conformance del registry de eventos: los 9 tipos
  `feedback.*`/`learning.*` con keys requeridas/extra y PII prohibida (0 texto
  libre en payloads) en `tests/contract/test_events_registry.py`
- [X] T010 [P] Escribir los tests de migración `0008` (upgrade desde vacío y
  desde `0007`, head único, drift, downgrade; uniques parciales
  `uq_feedback_events_active` y `uq_learning_proposals_pending`) en
  `tests/migrations/test_0008_feedback_learning.py`
- [X] T011 [P] Escribir los unit tests de repos (append-only de
  `learning_policy_versions`; cadena de supersede con `superseded_by`; uniques
  de idempotency y estado activo; shortlist `add`/`remove`) en
  `tests/unit/application/feedback/test_repositories.py`
- [X] T012 [P] Escribir los unit tests de los seams nuevos de `RadarService`
  (`bump_profile_version` versiona y snapshotea sin correr; `submit_run`
  encola `recommendation.run` con el triple unique y trigger `edited`) en
  `tests/unit/application/radar/test_profile_service.py`

### Implementation for Foundational

- [X] T013 Definir los valores puros y errores (`FeedbackEvent`,
  `DecisionState`, `QuickReason`, `LearningPolicyDoc`, `LearningProposal`,
  `ProposalChange`, `FeedbackError` y subclases tipadas) en
  `src/umbral/application/feedback/contracts.py`
- [X] T014 [P] Implementar el registry puro de quick reasons (loader del seed
  y `parse_reasons_v1`, `validate_reasons` contra el contrato y el concept
  registry) en `src/umbral/application/feedback/reasons.py`
- [X] T015 [P] Implementar el registry puro de learning policy (loader del
  seed y `parse_policy_v1`, `validate_policy`, versión inmutable) en
  `src/umbral/application/feedback/policy.py`
- [X] T016 [P] Implementar la state machine pura de decisión (supersede con
  compensación, no-op idempotente, guard de terminal para contacted; reglas
  `next_state`/`supersedes`) en `src/umbral/application/feedback/state.py`
- [X] T017 [P] Implementar `evaluate_signals` puro (cuenta señales like/dislike
  con razón ligada a concepto dentro de la ventana, min_signals, cooldown,
  expiración; 0 LLM; devuelve `ProposalDraft | None`) en
  `src/umbral/application/feedback/signals.py`
- [X] T018 [P] Definir los puertos `FeedbackEventRepository`,
  `LearningPolicyRepository`, `LearningProposalRepository`, `ShortlistPort`
  (add/remove) y `ListingReader` en `src/umbral/application/feedback/ports.py`
- [X] T019 Implementar los modelos y ENUMs de las 5 tablas
  (`feedback_events`, `feedback_event_reasons`, `learning_policies`,
  `learning_policy_versions`, `learning_proposals`) con constraints e índices
  únicos y registrarlos en `src/umbral/infrastructure/db/models/feedback.py` y
  `src/umbral/infrastructure/db/models/__init__.py`
- [X] T020 Crear la revisión `0008_feedback_learning` (down:
  `0007_scoring_explanations`) con las cinco tablas, los 3 ENUMs
  (`feedback_event_type`, `feedback_event_state`, `learning_proposal_state`)
  y los uniques parciales en `alembic/versions/0008_feedback_learning.py`
- [X] T021 [P] Implementar los repos SQLAlchemy (append-only de eventos con
  supersede transaccional, proposal lifecycle, uniques parciales) en
  `src/umbral/infrastructure/db/repositories/feedback.py`
- [X] T022 [P] Extender `SqlAlchemyShortlistRepository` con `add` (upsert al
  final, posición = tail) y `remove` (idempotente) en
  `src/umbral/infrastructure/db/repositories/scoring.py`
- [X] T023 [P] Implementar los adapters in-memory para tests en
  `tests/fakes/feedback.py`
- [X] T024 Implementar los loaders de contratos (quick reasons y learning
  policy) en `src/umbral/infrastructure/feedback/contract_loader.py`
- [X] T025 Añadir los settings `learning.*` (`policy_seed_version`
  `learning-v1`) y `feedback.*` (`quick_reasons_seed_version`
  `quick-reasons-v1`, `free_feedback_enabled` false,
  `max_free_feedback_length` 500) validados al iniciar en
  `src/umbral/infrastructure/config/settings.py` con su test
- [X] T026 Implementar los seams `bump_profile_version` (bump + snapshot sin
  submit) y `submit_run` (encola `recommendation.run` con trigger `edited`)
  en `src/umbral/application/radar/service.py`

**Checkpoint**: dominio puro, contratos, persistencia, settings y seams
disponibles y verificados; las historias pueden comenzar.

---

## Phase 3: User Story 1 — Expresar opinion en card y detalle con feedback inmutable (Priority: P0) MVP

**Goal**: `record_feedback` persiste cada acción (like, dislike, save, dismiss,
contacted) como evento inmutable con actor/contexto/timestamp, idempotente por
clave, con no-op y supersede por compensación; card y detalle ofrecen las
acciones con confirmación visible y undo (excepto contacted).

**Independent Test**: las cinco acciones desde card/detalle persisten un evento
inmutable con actor, contexto y timestamp; repetir la misma clave no duplica;
like→dislike→like produce tres eventos con compensación y el estado es el del
último; contacted es terminal; el undo revierte con compensación (SC-001,
SC-002, SC-003).

### Tests for User Story 1

> Escribir T027–T028 primero y confirmar que fallan por la conducta ausente.

- [X] T027 [P] [US1] Escribir los unit tests de `record_feedback` (replay por
  idempotency key, no-op del estado vigente, supersede con compensación,
  guard de terminal para contacted, validación de reason keys contra el seed,
  free_feedback opcional con límite) en
  `tests/unit/application/feedback/test_feedback_service.py`
- [X] T028 [P] [US1] Escribir los tests de integración de feedback events sobre
  DB real (cadena append-only con `superseded_by`, único activo por
  (profile, listing), replay sin duplicados, contacted terminal) en
  `tests/integration/feedback/test_feedback_events.py`
- [X] T029 [P] [US1] Escribir la conformance del endpoint POST feedback (DTOs,
  errores tipados `feedback_not_found`, `feedback_terminal`,
  `feedback_invalid_reason`, `feedback_conflict`, deny-by-default) en
  `tests/contract/test_feedback_endpoints.py`

### Implementation for User Story 1

- [X] T030 [US1] Implementar `record_feedback` y el cálculo del estado de
  decisión (idempotencia, no-op, supersede transaccional, guard de terminal,
  validación de reasons, evento `feedback.recorded.v1`) en
  `src/umbral/application/feedback/service.py`
- [X] T031 [P] [US1] Implementar `routers/feedback.py` (POST feedback con
  problemas tipados y autorización por acción `product.feedback.write`, patrón
  de `routers/explanations.py`) y registrarlo en `src/umbral/api/main.py`
- [X] T032 [P] [US1] Regenerar el cliente tipado desde OpenAPI y commitearlo
  (`npm run api:generate --workspace @umbral/web`) y añadir las funciones de
  feedback a `apps/web/src/lib/radar/client.ts`
- [X] T033 [P] [US1] Construir el componente de acciones de feedback
  (save/dismiss/like/dislike + reasons según `allowed_on`, estados optimistas
  reversibles, undo salvo contacted, confirmación visible) en
  `apps/web/src/components/radar/feedback-actions.tsx` y conectarlo a las
  cards del radar (`apps/web/src/app/(protected)/radar/[id]/page.tsx`) y al
  detalle (`apps/web/src/app/(protected)/listings/[id]/page.tsx`)
- [X] T034 [P] [US1] Verificar el build web (`npm run build --workspace
  @umbral/web`) y la accesibilidad por convención (teclado, labels, contraste)
  de las acciones de feedback

**Checkpoint**: feedback inmutable e idempotente verificado por conformance +
unit + integración y superficie web; US1 cerrada.

---

## Phase 4: User Story 2 — Shortlist y descartados persistentes (Priority: P0)

**Goal**: el save persiste la shortlist compartida (`comparison_shortlists`),
el un-save la remueve; el endpoint de decision-items filtra por estado; los
descartados quedan ocultos del radar por defecto con opción de mostrarlos; 0
runs se crean por feedback directo.

**Independent Test**: la shortlist sobrevive recarga y navegación por búsqueda;
el dismiss oculta del radar por defecto y se puede mostrar; guardar un
descartado revierte al último evento; el matches anota `decision_state`; 0
feedback directo crea runs; accesos ajenos se deniegan (SC-004).

### Tests for User Story 2

> Escribir T035–T036 primero y confirmar que fallan por la conducta ausente.

- [X] T035 [P] [US2] Escribir los unit tests de decision-items y save/un-save
  (upsert a `comparison_shortlists` en el mismo commit, remove idempotente,
  filtro por estado, overlay sin runs) en
  `tests/unit/application/feedback/test_decision_items.py`
- [X] T036 [P] [US2] Escribir los tests de integración de decision items sobre
  DB real (shortlist persistente por búsqueda, dismiss oculto + `include_dismissed`,
  matches con `decision_state`, 0 runs creados) en
  `tests/integration/feedback/test_decision_items.py`

### Implementation for User Story 2

- [X] T037 [US2] Implementar `list_decision_items`/`get_decision_state` y el
  upsert/remove de shortlist en `record_feedback` (save/un-save) en
  `src/umbral/application/feedback/service.py`
- [X] T038 [P] [US2] Implementar GET decision-items en `routers/feedback.py` y
  la anotación de `decision_state` + parámetro `include_dismissed` en
  `routers/matches.py`; regenerar el cliente (`npm run api:generate --workspace
  @umbral/web`) y añadir las funciones a `apps/web/src/lib/radar/client.ts`
- [X] T039 [P] [US2] Construir las vistas de shortlist y descartados por
  búsqueda (filtros por estado, retorno al detalle) en
  `apps/web/src/app/(protected)/radar/[id]/shortlist/page.tsx` y
  `apps/web/src/app/(protected)/radar/[id]/dismissed/page.tsx`
- [X] T040 [P] [US2] Emitir `feedback.shortlist_viewed.v1` y
  `feedback.dismissed_viewed.v1` desde el cliente
  (`apps/web/src/lib/radar/events.ts`) y verificar el build web

**Checkpoint**: shortlist y descartados verificados por unit + integración;
US2 cerrada.

---

## Phase 5: User Story 3 — Proponer aprendizaje desde señales (Priority: P0)

**Goal**: tras un like/dislike con razones, el servicio evalúa señales por
concepto contra la política versionada y crea una propuesta pendiente con
evidencia refs, alcance por búsqueda y efecto esperado; el banner del radar
descubre propuestas pendientes; 0 propuestas se aplican solas y 0 derivan de
save/dismiss/contacted.

**Independent Test**: 3 señales consistentes sobre el mismo concepto dentro de
la ventana crean una propuesta pendiente con evidencia; 2 no; save/dismiss/
contacted nunca proponen; cooldown y única pendiente por concepto; el banner
muestra la propuesta al abrir el radar (SC-005).

### Tests for User Story 3

> Escribir T041–T042 primero y confirmar que fallan por la conducta ausente.

- [X] T041 [P] [US3] Escribir los unit tests de señales y creación de propuesta
  (min_signals, ventana, cooldown, única pendiente por (profile, concept),
  contradicción → superada, 0 derivadas de save/dismiss/contacted) en
  `tests/unit/application/feedback/test_signals.py`
- [X] T042 [P] [US3] Escribir la conformance del listado de propuestas (DTOs,
  paginación, filtro por estado, deny-by-default) en
  `tests/contract/test_learning_endpoints.py`

### Implementation for User Story 3

- [X] T043 [US3] Integrar la evaluación de señales en el mismo commit de
  `record_feedback` (crear propuesta pendiente con `policy_version_id` y
  evidence_refs, evento `learning.proposal_created.v1`) e implementar
  `list_proposals(state)` en `src/umbral/application/feedback/service.py`
- [X] T044 [P] [US3] Implementar GET learning-proposals en
  `routers/learning.py` (autorización `product.learning.read`) y registrarlo
  en `src/umbral/api/main.py`; regenerar el cliente
  (`npm run api:generate --workspace @umbral/web`) y añadir la función a
  `apps/web/src/lib/radar/client.ts`
- [X] T045 [P] [US3] Construir el banner inline de propuesta pendiente
  (visible al abrir el radar, enlace al detalle de la propuesta con cambio
  exacto/alcance/efecto esperado) en
  `apps/web/src/components/radar/proposal-banner.tsx` y conectarlo en
  `apps/web/src/app/(protected)/radar/[id]/page.tsx`

**Checkpoint**: propuestas de aprendizaje verificadas por unit + conformance y
banner; US3 cerrada.

---

## Phase 6: User Story 4 — Confirmar, deshacer o ampliar aprendizaje (Priority: P0)

**Goal**: confirmar aplica la propuesta como preference fact
(`fact_source="learning.proposal"`), versiona perfil, compila y encola run;
deshacer revierte con fact de compensación y nuevo run; ampliar edita el cambio
pendiente mostrando el diff; rechazar/expiración son transiciones trazables.

**Independent Test**: confirmar muestra diff/alcance/efecto y crea fact+perfil+
run; deshacer revierte con compensación y el run intermedio queda consultable;
ampliar edita antes de confirmar; confirmar una expirada/superada se rechaza
con error accionable (SC-006).

### Tests for User Story 4

> Escribir T046–T047 primero y confirmar que fallan por la conducta ausente.

- [X] T046 [P] [US4] Escribir los unit tests del lifecycle de propuesta
  (confirm → fact+compile+bump+submit; undo → fact de compensación; expand →
  diff; reject; expiración lazy; guards de estado y concurrencia) en
  `tests/unit/application/feedback/test_proposal_lifecycle.py`
- [X] T047 [P] [US4] Escribir los tests de integración del lifecycle sobre DB
  real (confirm/undo crean runs con trigger `edited`, fact compensada,
  anterior congelado, expirada/superada rechazadas) en
  `tests/integration/feedback/test_proposal_lifecycle.py`
- [X] T048 [P] [US4] Escribir la conformance de los endpoints de propuesta
  (PUT expand y POST confirm/reject/undo con errores tipados
  `proposal_not_found`, `proposal_not_pending`, `proposal_expired`, 409
  concurrency) en `tests/contract/test_learning_endpoints.py`

### Implementation for User Story 4

- [X] T049 [US4] Implementar `confirm_proposal` (fact → bump → compile → submit
  run, applied refs), `reject_proposal`, `expand_proposal` (diff y eventos) y
  `undo_proposal` (fact de compensación + re-run) con guards de estado en
  `src/umbral/application/feedback/service.py`
- [X] T050 [P] [US4] Implementar PUT expand y POST confirm/reject/undo en
  `routers/learning.py` (autorización `product.learning.write`); regenerar el
  cliente (`npm run api:generate --workspace @umbral/web`) y añadir las
  funciones a `apps/web/src/lib/radar/client.ts`
- [X] T051 [P] [US4] Conectar las acciones del banner (confirmar, ampliar,
  descartar) y emitir los eventos `learning.proposal_confirmed/rejected/
  expanded/undone.v1` en `apps/web/src/components/radar/proposal-banner.tsx` y
  `src/umbral/application/feedback/service.py`

**Checkpoint**: lifecycle de propuestas verificado por unit + integración;
US4 cerrada.

---

## Phase 7: User Story 5 — Recalcular tras cambios relevantes (Priority: P0)

**Goal**: la orquestación del recalculado queda garantizada a nivel de run: el
confirm/undo versiona el perfil y crea un run nuevo atómico con la compilación
creada antes del submit; el run anterior queda congelado; un run fallido
conserva el último válido; el feedback directo 0 genera runs.

**Independent Test**: cada confirm/undo crea un run nuevo con trigger `edited`
y la compilación del nuevo profile version; el run anterior es consultable; un
fallo inducido a mitad conserva el último válido con causa y 0 parciales; el
feedback directo no genera runs nuevos (SC-007).

### Tests for User Story 5

> Escribir T052 primero y confirmar que falla por la conducta ausente.

- [X] T052 [P] [US5] Escribir los tests de integración del recalculado sobre DB
  real (run nuevo con trigger `edited` y compilación previa al submit, anterior
  congelado, fallo inducido conserva el último válido, feedback directo 0
  runs) en `tests/integration/feedback/test_recalculate.py`

### Implementation for User Story 5

- [X] T053 [US5] Ajustar la orquestación del recalculado (orden fact → bump →
  compile → submit garantizado, guards de idempotencia del run por triple
  unique, propagación de eventos `recommendation.run_published.v1`) en
  `src/umbral/application/feedback/service.py` y
  `src/umbral/application/radar/service.py`

**Checkpoint**: recalculado verificado sobre Postgres real; US5 cerrada.

---

## Phase 8: User Story 6 — Capturar feedback libre contextual (Priority: P1)

**Goal**: el like/dislike acepta texto libre opcional con límite y contexto; la
UI explica cómo se usará; 0 contenido de texto llega a eventos/analytics.

**Independent Test**: el texto libre es opcional y limitado; la UI explica su
uso y que no genera cambios automáticos; 0 texto en eventos ni analytics; un
like/dislike sin texto es válido (SC-008).

### Tests for User Story 6

> Escribir T054 primero y confirmar que falla por la conducta ausente.

- [X] T054 [P] [US6] Escribir la conformance de que 0 payloads de
  `feedback.recorded.v1` contienen texto libre y que el límite de longitud se
  valida en `tests/contract/test_events_registry.py` y
  `tests/unit/application/feedback/test_feedback_service.py`

### Implementation for User Story 6

- [X] T055 [P] [US6] Implementar la captura de feedback libre en
  `record_feedback` (opcional, límite `feedback.max_free_feedback_length`,
  contexto) detrás de `feedback.free_feedback_enabled` en
  `src/umbral/application/feedback/service.py`
- [X] T056 [P] [US6] Construir el input de feedback libre en
  `apps/web/src/components/radar/feedback-actions.tsx` (opcional, copy de uso
  "insumo cualitativo", 0 cambios automáticos) y verificarlo con
  `feedback.free_feedback_enabled=true`; verificar el build web
- [ ] T057 [P] [US6] Escribir los component tests del feedback libre (opcional,
  aviso de uso, límite de longitud) en
  `apps/web/src/components/radar/feedback-actions.test.tsx`

**Checkpoint**: feedback libre P1 verificado; US6 cerrada.

---

## Phase 9: User Story 7 — Mostrar historial de precio y cambios (Priority: P1)

**Goal**: el detalle muestra el historial de cambios confirmados de precio y
atributos con fecha y fuente (desde `known_changes`/listing versions), declara
"historial insuficiente" sin muestra y 0 infiere tendencias.

**Independent Test**: cada cambio mostrado tiene fecha y fuente; sin muestra se
declara historial insuficiente; 0 tendencias inferidas (SC-009).

### Tests for User Story 7

> Escribir T058 primero y confirmar que falla por la conducta ausente.

- [ ] T058 [P] [US7] Escribir los component tests de la sección de historial
  (cambios con fecha/fuente, estado insuficiente, 0 líneas de tendencia) en
  `apps/web/src/app/(protected)/listings/[id]/page.test.tsx`

### Implementation for User Story 7

- [X] T059 [P] [US7] Construir la sección de historial de precio/cambios en el
  detalle desde `known_changes` (fechas, fuentes, before/after, aviso de
  historial insuficiente, 0 tendencias) en
  `apps/web/src/app/(protected)/listings/[id]/page.tsx`
- [X] T060 [P] [US7] Verificar que el DTO de detalle incluye el historial
  completo (campos aditivos si faltan) y regenerar el cliente si aplica
  (`npm run api:generate --workspace @umbral/web`); verificar el build web

**Checkpoint**: historial de cambios P1 verificado; US7 cerrada.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: harness dedicado, evidencia de cierre y gate completo. Nada de
esto cambia el comportamiento de producto.

- [X] T061 Escribir el test de lineage completo (propuesta → feedback events
  → listing/run → perfil) y la ausencia de PII en eventos para el 100% del
  conjunto de prueba en `tests/integration/feedback/test_lineage.py`
- [X] T062 [P] Crear `scripts/check-feedback.ps1` (contract conformance + unit +
  integración feedback sobre testcontainers + build web) y registrarlo en
  `scripts/check.ps1`
- [X] T063 [P] Escribir la evidencia de cierre del incremento en
  `docs/runbooks/evidence/feedback-learning-acceptance.md` (resultado de cada
  SC del spec y recorrido de los escenarios de
  `specs/007-feedback-learning/quickstart.md`)
- [ ] T064 [P] Actualizar `docs/runbooks/runtime-local.md` y el quickstart del
  feature con los nuevos endpoints, settings `feedback.*`/`learning.*` y los
  9 eventos aditivos
- [ ] T065 Verificar el gate completo desde checkout limpio:
  `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`,
  `uv run pytest`, `uv run alembic current --check-heads`, `uv run alembic check`,
  `npm run build --workspace @umbral/web` y `.\scripts\check.ps1`; documentar
  el resultado en la evidencia de cierre

---

## Dependencies

- **Setup (Phase 1)**: sin dependencias; publica contratos y fixtures.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P0)**: depende de Foundational (state, reasons, repos, migración,
  seams); independiente de US2–US7.
- **US2 (P0)**: depende de Foundational (shortlist `add`/`remove`, T022) y de
  US1 (`record_feedback`, T030); independiente de US3–US7.
- **US3 (P0)**: depende de Foundational (`signals.py`, policy, repos) y de US1
  (registro de feedback); independiente de US2/US4/US5.
- **US4 (P0)**: depende de US3 (propuesta pendiente, T043) y de Foundational
  (seams de `RadarService`, T026; `record_preference_fact`/`compile_profile` de
  H3.1 existentes).
- **US5 (P0)**: depende de US4 (orquestación confirm/undo) y del run v1 de
  H3.2; cierra la garantía a nivel run.
- **US6 (P1)**: depende de US1 (record_feedback); independiente de US2–US5.
- **US7 (P1)**: independiente del resto (usa datos de H2.2/listings ya
  expuestos); se construye en paralelo con US1–US6.
- **Polish (final)**: depende de las historias deseadas (T061/T062/T063/T064
  son paralelizables con las historias tardías).

### User Story Dependencies

- **US1**: `state.py` (T016) + `reasons.py` (T014) + repos (T021/T023) +
  `record_feedback` (T030) + router (T031) + web (T033).
- **US2**: reusa `record_feedback`; agrega shortlist add/remove (T022/T037) y
  decision-items (T037/T038) + vistas (T039/T040).
- **US3**: reusa `signals.py` (T017) + `policy.py` (T015); agrega evaluación
  en `record_feedback` (T043) + listado (T044) + banner (T045).
- **US4**: reusa propuesta pendiente; agrega lifecycle completo (T049) +
  endpoints (T050) + acciones del banner (T051).
- **US5**: reusa orquestación de US4; agrega garantía de run (T053).
- **US6**: reusa `record_feedback`; agrega captura P1 (T055/T056/T057).
- **US7**: datos existentes; agrega sección web (T059/T060).
- Trabajo secuencial recomendado: US1 → US2 → US3 → US4 → US5 → (US6 ∥ US7 ∥
  Polish) → Polish.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Dominio puro antes de servicio; servicio antes de routers; routers antes de
  web.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003/T004/T005/T006 en Setup; T008–T012, T014–T018, T021–T024, T026 en
  Foundational; T027/T028/T029 en US1; T035/T036 en US2; T041/T042 en US3;
  T046/T047/T048 en US4; T052 en US5; T054 en US6; T058 en US7;
  T061/T062/T063/T064 en Polish — tocan archivos distintos sin dependencias.
- Tras Foundational, US1 y US7 pueden empezar en paralelo; tras US1, US2 y US3
  en paralelo; US4 sigue a US3; US5 sigue a US4; US6 sigue a US1.

---

## Parallel Example: User Story 1

```bash
# Tests de US1 en paralelo:
Task: "Unit tests de record_feedback en tests/unit/application/feedback/test_feedback_service.py"
Task: "Integración de feedback events en tests/integration/feedback/test_feedback_events.py"
Task: "Conformance del endpoint POST feedback en tests/contract/test_feedback_endpoints.py"

# Implementación en paralelo (archivos distintos):
Task: "record_feedback en src/umbral/application/feedback/service.py"
Task: "Router feedback.py en src/umbral/api/routers/feedback.py"
Task: "Componente feedback-actions.tsx en apps/web/src/components/radar/feedback-actions.tsx"
```

---

## Implementation Strategy

### MVP First (Camino crítico P0 del backlog)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar US1 a US5 en orden (feedback inmutable → shortlist/descartados →
   propuestas → confirmar/deshacer/ampliar → recalculado): cubren UM-H3-023 a
   UM-H3-030.
4. **STOP y VALIDAR** cada historia con su Independent Test sobre
   Postgres/PostGIS real antes de continuar.
5. Primer recorrido interno del hito completo: US1–US5 con harness y build
   web.
6. Demo/entrega si corresponde; US6 y US7 (P1) después.

### Incremental Delivery

1. Setup + Foundational → contratos, dominio puro y persistencia listos.
2. US1 → feedback inmutable + acciones web → validar → demo (MVP).
3. US2 → shortlist y descartados → validar.
4. US3 → propuestas de aprendizaje → validar.
5. US4 → confirmar/deshacer/ampliar → validar.
6. US5 → recalculado con runs nuevos → validar (camino crítico
   UM-H3-023..030).
7. US6 → feedback libre → validar (P1).
8. US7 → historial de precio y cambios → validar (P1).
9. Polish → lineage, harness, evidencia de cierre.

### Parallel Team Strategy

1. Equipo completo Setup + Foundational juntos.
2. Tras Foundational: US1 y US7 en paralelo (US7 no depende de nada nuevo).
3. Tras US1: US2, US3 y US6 en paralelo; US4 sigue a US3; US5 sigue a US4.
4. Polish prepara lineage y evidencia en paralelo con US6/US7.
5. Las historias integran sin romperse entre sí (tablas, repos, routers y
   eventos separados; el registry de eventos crece aditivamente).

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
- No agregar dependencias de Python nuevas (todo lo necesario ya existe).
- No crear un job nuevo: la evaluación de señales es síncrona dentro de
  `record_feedback` (R-07); el recalculado reutiliza el job `recommendation.run`
  existente con trigger `edited` (R-08).
- Solo like/dislike con razones ligadas a concepto cuentan como señales
  (clarificación); save/dismiss/contacted nunca proponen.
- La shortlist del producto es `comparison_shortlists` (persistencia compartida
  con el comparador P1 de H3.2); el gate `scoring.comparator_enabled` sigue
  gobernando solo los endpoints del comparador.
- Los eventos nuevos se registran en `contracts/events/v1/events-registry.json`
  y se emiten con los patrones existentes (`_emit_server_event`/
  `record_client_event`); 0 texto de feedback libre en payloads.
- El feedback libre (US6) queda detrás de `feedback.free_feedback_enabled=false`
  hasta el primer recorrido interno del hito.
- El copy del feedback libre y del historial se revisa con producto según
  UM-H0-007 antes del release.
- Los contratos nuevos se registran en `src/umbral/api/main.py` y regeneran el
  cliente TS (`npm run api:generate --workspace @umbral/web`) al publicar sus
  DTOs.
