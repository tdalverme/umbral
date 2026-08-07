# Tasks: Scoring and Explanations

**Input**: Design documents from `specs/006-scoring-explanations/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice
starts with the failing contract/unit/integration test named here"). En cada
fase se escriben primero los tests indicados y se confirma que fallan por la
conducta ausente antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido
(contratos `scoring/v1`, eventos aditivos, políticas puras: policy,
evaluadores, engine, explicaciones, comparación; puertos, persistencia y
migración `0007`). US1 entrega el registro de policy versionada; US2 el
ensamblado de evaluaciones por evaluador; US3 la semántica desconocido vs
negativo; US4 el scoring determinista en el pipeline del run; US5 la
publicación atómica con evaluaciones; US6 las explicaciones deterministas;
US7 los contratos HTTP de explicación; US8 la comparación estructurada;
US9 la web de razones/incertidumbre; US10 el comparador persistente (P1).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos machine-checkable de scoring y
explicaciones, el registry de eventos ampliado, el conjunto golden y los
límites de arquitectura que usarán todas las historias.

- [X] T001 Definir el contrato de scoring policy machine-checkable (documento
  de policy con criteria/weights/normalization/gates/confidence/bonuses/
  penalties/tie_break y seed v1 `scoring-policy-v1`) en
  `contracts/scoring/v1/scoring-policy-v1.json`
- [X] T002 [P] Definir el contrato de explicaciones machine-checkable (reason
  codes por state, evidence levels strong/medium/low con umbrales, copy
  templates deterministas y `notice.legacy_run`) en
  `contracts/scoring/v1/explanations-v1.json`
- [X] T003 [P] Ampliar el registry cerrado de eventos con los 2 tipos
  `recommendation.*` (`explanation_viewed.v1`, `comparison_viewed.v1`;
  payloads sólo ids/versiones/conteos; forbidden: valores de evaluación,
  evidencia, texto) en `contracts/events/v1/events-registry.json`
- [X] T004 [P] Crear el conjunto golden de scoring (policy válidas e
  inválidas: pesos no normalizables, matcher type desconocido, params fuera
  de allowed_params, gate no soportado; casos por evaluador con score/
  confianza/state esperados; casos desconocido vs mismatch; explicaciones
  con copy esperado; matrices de comparación) en
  `tests/fixtures/scoring/policy-golden.json`,
  `tests/fixtures/scoring/evaluators-golden.json`,
  `tests/fixtures/scoring/explanations-golden.json` y
  `tests/fixtures/scoring/comparison-golden.json` (reusando fixtures de
  003/004/005)
- [X] T005 [P] Añadir fixtures de arquitectura para los límites de
  `application/scoring` (permite application→domain y adapters→application;
  prohíbe domain→infrastructure, scoring→FastAPI/web/LLM directo, y engine
  con imports de I/O) en `tests/architecture/test_scoring_boundaries.py`

**Checkpoint**: contratos publicados, registry ampliado, conjunto golden
disponible y límites nuevos verificados desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Políticas puras (policy registry, evaluadores, engine,
explicaciones, comparación), puertos, persistencia y migración `0007`. Nada
de las historias comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T006 Escribir la conformance de scoring policy: parse/validación
  (weights normalizables, matcher types y params de `matcher-types-v1.json`,
  conceptos del seed o criterios fijos, gates soportados, tie_break) y seed
  `scoring-policy-v1` cargable en `tests/contract/test_scoring_policy.py`
- [X] T007 [P] Escribir la conformance de evaluadores: casos golden por
  matcher type (numeric_range, categorical, geo_proximity, semantic_feature)
  con score/confianza/state/evidencia esperados bajo el contrato común;
  params inválidos rechazados; sin datos → `unknown` con confianza baja en
  `tests/contract/test_evaluators.py`
- [X] T008 [P] Escribir la conformance de explicaciones: razones con
  evidence refs, riesgos, missing data y confianza desde evaluaciones;
  doble llamada produce copy idéntico; niveles de evidencia por umbrales en
  `tests/contract/test_explanations.py`
- [X] T009 [P] Escribir la conformance de comparación: límite 2..N,
  duplicados rechazados, dimensiones fijas + criterios activos, celdas
  faltantes visibles, 0 ganador en `tests/contract/test_comparison.py`
- [X] T010 [P] Ampliar la conformance del registry de eventos: los 2 tipos
  `recommendation.*` con keys requeridas/extra y PII prohibida en
  `tests/contract/test_events_registry.py`
- [X] T011 [P] Escribir los tests de migración `0007` (upgrade desde vacío y
  desde `0006`, head único, drift, downgrade) en
  `tests/migrations/test_0007_scoring_explanations.py`
- [X] T012 [P] Escribir los unit tests de repos (append-only de
  `scoring_policy_versions`; unicidad `uq_criterion_evaluations_run_listing_criterion`;
  shortlist idempotente) en `tests/unit/application/scoring/test_repositories.py`

### Implementation for Foundational

- [X] T013 Definir los valores puros y errores (`ScoringPolicy`,
  `PolicyVersion`, `Evaluation`, `CriterionEvaluation`, `Explanation`,
  `Comparison`, `ComparisonCell`, `ScoringError`) en
  `src/umbral/application/scoring/contracts.py`
- [X] T014 [P] Implementar el registry puro de policy (loader del seed y
  `parse_policy_v1`, `validate_policy` contra el contrato, rechazo sin
  parciales) en `src/umbral/application/scoring/policy.py`
- [X] T015 [P] Implementar los 4 evaluadores puros con contrato común
  (numeric_range, categorical, geo_proximity, semantic_feature sobre
  observaciones de H3.1; `unknown` nunca mismatch) en
  `src/umbral/application/scoring/evaluators.py`
- [X] T016 [P] Implementar `score_candidates` puro (weights, gates, bonuses,
  penalizaciones, tie-break; 0 I/O; score 0..1 redondeado) en
  `src/umbral/application/scoring/engine.py`
- [X] T017 [P] Implementar `build_explanation` puro (razones/riesgos/
  missing/confianza con evidence refs, copy por templates deterministas,
  niveles de evidencia) en `src/umbral/application/scoring/explanations.py`
- [X] T018 [P] Implementar `compare_listings` puro (límite, dimensiones
  fijas + criterios activos, celdas con missing, 0 ganador) en
  `src/umbral/application/scoring/comparison.py`
- [X] T019 [P] Definir los puertos `PolicyRepository`, `EvaluationRepository`,
  `ShortlistRepository` en `src/umbral/application/scoring/ports.py`
- [X] T020 Implementar los modelos y ENUM (`evaluation_state` match/mismatch/
  unknown) de las 4 tablas (`scoring_policies`, `scoring_policy_versions`,
  `criterion_evaluations`, `comparison_shortlists`) con constraints e índices
  únicos y registrarlos en `src/umbral/infrastructure/db/models/scoring.py` y
  `src/umbral/infrastructure/db/models/__init__.py`
- [X] T021 Crear la revisión `0007_scoring_explanations` (down:
  `0006_criteria_observations`) con las cuatro tablas, el ENUM y los chequeos
  de extensión PostGIS/pgvector en
  `alembic/versions/0007_scoring_explanations.py`
- [X] T022 [P] Implementar los repos SQLAlchemy (sin commit propio, append-only
  de policy, evaluación por run congelada) en
  `src/umbral/infrastructure/db/repositories/scoring.py`
- [X] T023 [P] Implementar los adapters in-memory para tests en
  `tests/fakes/scoring.py`
- [X] T024 Añadir los settings `scoring.*` (`policy_seed_version`
  `scoring-policy-v1`, `legacy_score_policy_version` `scoring-baseline-v1`,
  `comparison_max_listings` 6, `comparator_enabled` false,
  `explanations_copy_contract_version` 1) validados al iniciar en
  `src/umbral/infrastructure/config/settings.py` con su test

**Checkpoint**: políticas puras, contratos, persistencia y settings
disponibles y verificados; las historias pueden comenzar.

---

## Phase 3: User Story 1 — Definir la scoring policy v1 versionada (Priority: P0) MVP

**Goal**: la policy v1 queda poblada desde el seed versionado al construir el
servicio y `register_policy_version` permite registrar/editar policies con
versiones inmutables, rechazando documentos inválidos sin persistir parciales.

**Independent Test**: registrar el seed `scoring-policy-v1` produce
`scoring_policies` + `scoring_policy_versions` v1; una edición crea la
versión siguiente sin mutar la previa; pesos no normalizables, matcher types
desconocidos, params inválidos o gates no soportados se rechazan sin datos
parciales; cada policy registrada es consultable por versión (SC-002).

### Tests for User Story 1

> Escribir T025 primero y confirmar que falla por la conducta ausente.

- [X] T025 [P] [US1] Escribir los unit tests de `register_policy_version`
  (persistencia append-only, rechazo de documentos inválidos sin parciales,
  seed cargado al construir el servicio, consulta por versión) en
  `tests/unit/application/scoring/test_policy_service.py`

### Implementation for User Story 1

- [X] T026 [US1] Implementar `register_policy_version` y el loader del seed en
  `ScoringService` en `src/umbral/application/scoring/service.py`
- [X] T027 [P] [US1] Implementar la composición del servicio de scoring con
  repos SQLAlchemy + seed en `src/umbral/infrastructure/scoring/composition.py`

**Checkpoint**: policy versionada verificada por conformance + unit tests
sobre repos in-memory; US1 cerrada.

---

## Phase 4: User Story 2 — Evaluar con evaluadores genericos (Priority: P0)

**Goal**: el servicio ensambla evaluaciones de criterio a partir de los
evaluadores puros: valida params contra `allowed_params`, despacha por
matcher type, y produce el `CriterionEvaluation` (score, confianza, state,
reason_code, evidence_refs) listo para persistir.

**Independent Test**: cada caso golden por matcher type produce score,
confianza, state y evidencia esperados bajo el contrato común; params no
soportados se rechazan con error accionable; sin datos suficientes el
resultado es `unknown` con confianza baja y evidencia ausente, sin inventar
puntaje (SC-003).

### Tests for User Story 2

> Escribir T028 primero y confirmar que falla por la conducta ausente.

- [X] T028 [P] [US2] Escribir los unit tests de `evaluate_criterion`
  (dispatch por matcher type, validación de params, armado de
  `CriterionEvaluation` con input_refs de observaciones versionadas,
  `unknown` sin inventar puntaje) en
  `tests/unit/application/scoring/test_evaluation_service.py`

### Implementation for User Story 2

- [X] T029 [US2] Implementar `evaluate_criterion` (validación de params por
  `matcher-types-v1.json`, dispatch al evaluador, armado de la evaluación con
  reason_code y evidence_refs) en `src/umbral/application/scoring/service.py`

**Checkpoint**: evaluadores verificados a través del servicio con repos
in-memory; US2 cerrada.

---

## Phase 5: User Story 3 — Distinguir desconocido de evidencia negativa (Priority: P0)

**Goal**: la semántica de confianza del run se integra al engine: `unknown`
contribuye neutro, aplica la penalización de confianza de la policy y nunca
cuenta como mismatch; ambos estados se serializan de forma distinguible.

**Independent Test**: un criterio sin datos produce `unknown` con confianza
baja y 0 penalización de mismatch; un criterio con datos que no cumplen
produce `mismatch` con su contribución; la confianza del run refleja la
penalización por desconocido; la serialización de `unknown` y `mismatch` es
distinguible en todo el contrato (SC-004).

### Tests for User Story 3

> Escribir T030 primero y confirmar que falla por la conducta ausente.

- [X] T030 [P] [US3] Escribir los unit tests de la agregación de confianza del
  run (penalización por `unknown` según policy, neutralidad de contribución,
  ítems `unknown` nunca contados como mismatch, orden estable) en
  `tests/unit/application/scoring/test_unknown_semantics.py`
- [X] T031 [P] [US3] Escribir la conformance de serialización de estados
  (`match`/`mismatch`/`unknown` distinguibles en el DTO de evaluación y en la
  explicación) en `tests/contract/test_evaluation_states.py`

### Implementation for User Story 3

- [X] T032 [US3] Implementar la agregación de confianza del run y la
  neutralidad de `unknown` según la policy (penalización configurable) en
  `src/umbral/application/scoring/engine.py`

**Checkpoint**: semántica desconocido vs negativo verificada; US3 cerrada.

---

## Phase 6: User Story 4 — Evaluar criterios y calcular scoring v1 deterministico (Priority: P0)

**Goal**: `process_run_scoring` integra el engine en el pipeline del run:
perfil congelado + compilación de criterios (H3.1) + observaciones →
`score_candidates` → evaluaciones en memoria con inputs versionados, sin I/O
durante el cálculo.

**Independent Test**: ejecutar el scoring dos veces sobre la misma entrada
produce orden y desglose idénticos y 0 invocaciones dependen de red,
almacenamiento o modelo externo; cada evaluación persiste criterio, inputs
versionados, contribución y razón; evaluaciones de runs no publicados no se
usan en vistas (SC-001, SC-005).

### Tests for User Story 4

> Escribir T033–T034 primero y confirmar que fallan por la conducta ausente.

- [X] T033 [P] [US4] Escribir los unit tests de `process_run_scoring`
  (perfil+compilación+observaciones → evaluaciones con input_refs de
  observaciones versionadas, contribución y razón; doble ejecución idéntica)
  en `tests/unit/application/scoring/test_run_scoring.py`
- [X] T034 [P] [US4] Escribir los tests de integración de lineage de
  evaluaciones (evaluación → observación con versión → silver → Bronze)
  sobre DB real en `tests/integration/scoring/test_evaluation_lineage.py`

### Implementation for User Story 4

- [X] T035 [US4] Implementar `process_run_scoring` (cargar compilación del
  profile version + observaciones activas, ejecutar `score_candidates`,
  armar evaluaciones sin persistir) en `src/umbral/application/scoring/service.py`

**Checkpoint**: scoring determinista y evaluaciones con lineage verificados;
US4 cerrada.

---

## Phase 7: User Story 5 — Publicar recommendation runs atomicos (Priority: P0)

**Goal**: `process_run` publica run + items + `criterion_evaluations` +
`recommendation.run_published.v1` en una transacción (patrón `record_outcome`);
el engine v1 reemplaza al baseline; un run fallido conserva el último válido;
los runs legacy (`scoring-baseline-v1`) no se tocan y un recompute de
observaciones no invalida runs publicados.

**Independent Test**: un run exitoso congela snapshots, candidate set, policy
y score version antes de publicar y persiste sus evaluaciones en la misma
transacción; un fallo inducido a mitad conserva el último run válido con
causa y 0 parciales; el replay del job no duplica items ni evaluaciones; un
cambio de observaciones posterior no invalida el run publicado; los runs
legacy siguen servidos por matches (SC-006).

### Tests for User Story 5

> Escribir T036–T038 primero y confirmar que fallan por la conducta ausente.

- [X] T036 [P] [US5] Escribir los unit tests de la publicación atómica
  (run+items+evaluaciones+evento en una transacción; fallo → estado
  `failed` con `failure_code`; 0 evaluaciones parciales) en
  `tests/unit/application/scoring/test_run_publish.py`
- [X] T037 [P] [US5] Escribir los tests de integración del run v1 (publicación
  atómica sobre DB real, fallo inducido sin parciales, replay idempotente,
  legacy intacto, recompute de observaciones no invalida el run) en
  `tests/integration/scoring/test_run_v1.py`
- [X] T038 [P] [US5] Escribir los tests del handler extendido (resumen <= 8 KiB
  con conteos y `score_policy_version`, `failure_code` propagado) en
  `tests/unit/workers/test_run_handler_scoring.py`

### Implementation for User Story 5

- [X] T039 [US5] Implementar la publicación atómica de evaluaciones en
  `process_run` (persistir run+items+evaluaciones+evento juntos; fallo sin
  parciales) en `src/umbral/application/radar/service.py` y
  `src/umbral/application/scoring/service.py`
- [X] T040 [P] [US5] Reemplazar el engine baseline por scoring v1 en el
  pipeline del run (baseline conservado como referencia; legacy detectado por
  `scoring.legacy_score_policy_version`) en
  `src/umbral/application/radar/service.py` y
  `src/umbral/workers/radar.py`

**Checkpoint**: runs v1 atómicos verificados sobre Postgres real; US5
cerrada.

---

## Phase 8: User Story 6 — Explicar recomendaciones desde evidencia (Priority: P0)

**Goal**: el servicio arma explicaciones deterministas desde las evaluaciones
congeladas del run: razones con evidence refs y niveles de evidencia, riesgos,
datos faltantes y confianza global, con copy por templates del contrato y 0
afirmaciones fuera del desglose.

**Independent Test**: dos llamadas sobre el mismo run producen la misma
explicación (copy idéntico); el 100% de las razones cita evidence refs o
declara `unknown`; riesgos y faltantes derivan del breakdown; un criterio con
confianza baja declara su riesgo y faltante; 0 afirmaciones sin evidencia
interna (SC-007).

### Tests for User Story 6

> Escribir T041–T042 primero y confirmar que fallan por la conducta ausente.

- [X] T041 [P] [US6] Escribir los unit tests de `get_explanation` (razones con
  evidence refs y niveles, riesgos, missing data, confianza global; doble
  llamada copy idéntico; legacy → `explanation_unavailable`) en
  `tests/unit/application/scoring/test_explanation_service.py`
- [X] T042 [P] [US6] Escribir la conformance de copy (cadenas golden contra
  `explanations-v1.json`: reason codes por state, notice de legacy, formato
  score+confianza) en `tests/contract/test_explanation_copy.py`

### Implementation for User Story 6

- [X] T043 [US6] Implementar `get_explanation` (ensamblado desde evaluaciones
  del run con templates del contrato, niveles de evidencia por umbrales,
  guard de legacy) en `src/umbral/application/scoring/service.py`

**Checkpoint**: explicaciones deterministas con evidencia verificadas; US6
cerrada.

---

## Phase 9: User Story 7 — Exponer la explicacion por listing y por busqueda (Priority: P0)

**Goal**: la Product API expone explicación por listing y lista paginada por
búsqueda con score version, profile snapshot, feature snapshot, criterios y
evidence refs; deny-by-default por ownership del run y errores tipados.

**Independent Test**: consultar la explicación de un listing del run devuelve
el desglose completo; la lista por búsqueda pagina por keyset sin mezclar
versiones de policy; un listing fuera del run, un run legacy o una búsqueda
ajena se deniegan con problemas tipados sin filtrar datos (SC-008).

### Tests for User Story 7

> Escribir T044–T045 primero y confirmar que fallan por la conducta ausente.

- [X] T044 [P] [US7] Escribir la conformance de los endpoints de explicación
  (per-listing y lista paginada: DTOs, errores tipados
  `explanation_unavailable`/not found/forbidden, deny-by-default) en
  `tests/contract/test_explanation_endpoints.py`
- [X] T045 [P] [US7] Escribir los unit tests de `list_explanations` (keyset por
  `run_id` + posición, ownership del run, sin mezclar versiones de policy) en
  `tests/unit/application/scoring/test_explanation_service.py`

### Implementation for User Story 7

- [X] T046 [US7] Implementar `get_explanation` y `list_explanations` en el
  servicio (membership por run, paginación keyset, guard de legacy) en
  `src/umbral/application/scoring/service.py`
- [X] T047 [P] [US7] Implementar `routers/explanations.py` (2 endpoints GET con
  problemas tipados y autorización por acción, patrón de
  `routers/matches.py`) en `src/umbral/api/routers/explanations.py` y
  registrarlo en `src/umbral/api/main.py`
- [X] T048 [P] [US7] Regenerar el cliente tipado desde OpenAPI y commitearlo
  (`npm run api:generate --workspace @umbral/web`) tras publicar los DTOs

**Checkpoint**: contratos de explicación verificados por conformance +
denials; US7 cerrada.

---

## Phase 10: User Story 8 — Comparar listings de forma estructurada (Priority: P0)

**Goal**: el servicio valida 2..límite listings del último run publicado del
radar y construye la matriz con dimensiones fijas básicas + criterios activos
del perfil con valor, evidencia y estado faltante; el endpoint POST compara
sin inventar ganador.

**Independent Test**: hasta el límite se compara con dimensiones homogéneas;
celdas sin datos se muestran como faltantes (0 como valor negativo o
mismatch); más del límite, duplicados o listings de otras búsquedas se
rechazan con errores accionables; 0 ganador (SC-009).

### Tests for User Story 8

> Escribir T049–T050 primero y confirmar que fallan por la conducta ausente.

- [X] T049 [P] [US8] Escribir los unit tests de `build_comparison` (límite,
  duplicados, membership del último run, dimensiones fijas + criterios
  activos con estado por celda, faltantes visibles, 0 ganador) en
  `tests/unit/application/scoring/test_comparison_service.py`
- [X] T050 [P] [US8] Escribir la conformance del endpoint de comparación
  (DTOs de matriz y celdas, errores tipados `comparison_limit_exceeded`,
  `comparison_duplicate_listing`, `comparison_not_in_radar`,
  `explanation_unavailable` para run legacy) en
  `tests/contract/test_comparison_endpoint.py`

### Implementation for User Story 8

- [X] T051 [US8] Implementar `build_comparison` (validación de límite y
  membership, armado de celdas con evidencia y faltantes) en
  `src/umbral/application/scoring/service.py`
- [X] T052 [P] [US8] Implementar `routers/comparisons.py` (POST comparisons con
  problemas tipados y autorización por acción) en
  `src/umbral/api/routers/comparisons.py` y registrarlo en
  `src/umbral/api/main.py`
- [X] T053 [P] [US8] Regenerar el cliente tipado desde OpenAPI y commitearlo
  (`npm run api:generate --workspace @umbral/web`) tras publicar los DTOs

**Checkpoint**: comparación estructurada verificada por conformance; US8
cerrada.

---

## Phase 11: User Story 9 — Mostrar razones, riesgos e incertidumbre en la web (Priority: P0)

**Goal**: las cards del radar muestran hasta 3 razones con niveles de
evidencia y el detalle el desglose completo (razones, riesgos, datos
faltantes, confianza); los runs legacy muestran el score con el notice; 0
scores presentados como certeza; la web emite
`recommendation.explanation_viewed.v1`.

**Independent Test**: cards y detalle distinguen evidencia fuerte/media/baja
y desconocidos; un run legacy muestra el notice sin razones fabricadas; el
score siempre se presenta con su confianza; las vistas emiten su evento
versionado (SC-011).

### Tests for User Story 9

> Escribir T054 primero y confirmar que falla por la conducta ausente.

- [ ] T054 [P] [US9] Escribir los component tests web (cards con ≤3 razones y
  badges de evidencia; detalle con desglose y faltantes; notice de legacy;
  score+confianza; estados de carga/error/vacío) en
  `apps/web/src/app/(protected)/radar/[id]/page.test.tsx` y
  `apps/web/src/app/(protected)/listings/[id]/page.test.tsx`
  (DIFERIDA: sigue el diferimiento de tests web dedicados de H2.3; la
  verificación web es build + recorrido manual del quickstart)

### Implementation for User Story 9

- [X] T055 [US9] Actualizar las cards del radar para consumir
  `list_explanations` (razones principales con nivel de evidencia, score con
  confianza, notice de legacy) en `apps/web/src/app/(protected)/radar/[id]/page.tsx`
  y componentes de card en `apps/web/src/components/radar/`
- [X] T056 [P] [US9] Actualizar el detalle de listing para mostrar el desglose
  completo (razones, riesgos, datos faltantes, confianza, filtros cumplidos)
  en `apps/web/src/app/(protected)/listings/[id]/page.tsx`
- [X] T057 [P] [US9] Emitir `recommendation.explanation_viewed.v1` desde el
  cliente al ver explicaciones y verificar el build web
  (`npm run build --workspace @umbral/web`) en
  `apps/web/src/lib/radar/events.ts`

**Checkpoint**: web de razones/incertidumbre verificada por component tests y
build; US9 cerrada.

---

## Phase 12: User Story 10 — Construir el comparador persistente (Priority: P1; slice P1, post primer recorrido)

**Goal**: la shortlist persiste por búsqueda (GET/PUT idempotente con
membership del radar), la matriz responsive usa el contrato de comparación
con dimensiones auditables y navegación al detalle
(`scoring.comparator_enabled=false` por default).

**Independent Test**: la shortlist sobrevive recarga y navegación, respeta el
límite y pertenece a su búsqueda; la matriz es usable en desktop/mobile con
dimensiones fijas + criterios y celdas faltantes visibles; agregar más del
límite se rechaza con indicación (SC-012).

### Tests for User Story 10

> Escribir T058 primero y confirmar que falla por la conducta ausente.

- [X] T058 [P] [US10] Escribir los unit tests de shortlist (GET/PUT idempotente,
  límite, membership del run, deny-by-default) en
  `tests/unit/application/scoring/test_shortlist_service.py`
- [X] T059 [P] [US10] Escribir los tests de integración de shortlist sobre DB
  real (unicidad `(profile_id, listing_id)`, reemplazo idempotente) en
  `tests/integration/scoring/test_shortlist.py`

### Implementation for User Story 10

- [X] T060 [US10] Implementar `get_shortlist`/`set_shortlist` (reemplazo
  idempotente, límite y membership) en `src/umbral/application/scoring/service.py`
- [X] T061 [P] [US10] Implementar los endpoints GET/PUT de shortlist en
  `routers/comparisons.py` + setting `scoring.comparator_enabled` y
  regenerar el cliente (`npm run api:generate --workspace @umbral/web`)
- [X] T062 [P] [US10] Construir la ruta del comparador (matriz responsive con
  dimensiones fijas + criterios, celdas faltantes, navegación al detalle)
  en `apps/web/src/app/(protected)/radar/[id]/compare/page.tsx`

**Checkpoint**: comparador P1 verificado; US10 cerrada.

---

## Phase 13: Polish & Cross-Cutting Concerns

**Purpose**: harness dedicado, evidencia de cierre y gate completo. Nada de
esto cambia el comportamiento de producto.

- [X] T063 Escribir el test de lineage completo (evaluación → observación con
  versión → `silver_listings` → snapshot Bronze) para el 100% de las
  evaluaciones del conjunto de prueba en
  `tests/integration/scoring/test_lineage.py`
- [X] T064 [P] Crear `scripts/check-scoring.ps1` (contract conformance + unit +
  integración scoring sobre testcontainers + build web) y registrarlo en
  `scripts/check.ps1`
- [X] T065 [P] Escribir la evidencia de cierre del incremento en
  `docs/runbooks/evidence/scoring-explanations-acceptance.md` (resultado de
  cada SC del spec y recorrido de los escenarios de
  `specs/006-scoring-explanations/quickstart.md`)
- [X] T066 [P] Actualizar `docs/runbooks/runtime-local.md` y el quickstart del
  feature con los nuevos endpoints, settings `scoring.*` y el reemplazo del
  engine en `recommendation.run`
- [X] T067 Verificar el gate completo desde checkout limpio:
  `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`,
  `uv run pytest`, `uv run alembic current --check-heads`, `uv run alembic check`,
  `npm run build --workspace @umbral/web` y `.\scripts\check.ps1`; documentar
  el resultado en la evidencia de cierre

---

## Dependencies

- **Setup (Phase 1)**: sin dependencias; publica contratos y fixtures.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P0)**: depende de Foundational; independiente de US2–US10.
- **US2 (P0)**: depende de Foundational (evaluadores puros, T015);
  independiente de US1.
- **US3 (P0)**: depende de Foundational (engine, T016); independiente de
  US1/US2.
- **US4 (P0)**: depende de US2 (ensamblado de evaluaciones, T029) y US3
  (semántica unknown, T032).
- **US5 (P0)**: depende de US4 (`process_run_scoring`, T035) y Foundational.
- **US6 (P0)**: depende de US5 (evaluaciones del run publicadas) y
  Foundational.
- **US7 (P0)**: depende de US6 (explicaciones, T043) y US5.
- **US8 (P0)**: depende de US5 (último run publicado + evaluaciones);
  independiente de US6/US7.
- **US9 (P0)**: depende de US7 (endpoints de explicación, T047).
- **US10 (P1, slice P1)**: depende de US8 (comparación, T051) y US9 (patrones
  web).
- **Polish (final)**: depende de las historias deseadas (T063/T064/T065/T066
  son paralelizables con las historias tardías).

### User Story Dependencies

- **US1**: `policy.py` (T014) + repos (T022/T023) + `register_policy_version`
  (T026) + composición (T027).
- **US2**: reusa `evaluators.py` (T015); agrega `evaluate_criterion` (T029).
- **US3**: reusa `engine.py` (T016); agrega agregación de confianza (T032).
- **US4**: reusa engine + compilaciones de H3.1; agrega `process_run_scoring`
  (T035).
- **US5**: reusa `process_run_scoring`; agrega publicación atómica (T039) y
  el reemplazo del baseline (T040).
- **US6**: reusa evaluaciones publicadas; agrega `get_explanation` (T043).
- **US7**: reusa `get_explanation`; agrega listado y routers (T046/T047/T048).
- **US8**: reusa evaluaciones del último run; agrega `build_comparison` (T051)
  y el router (T052/T053).
- **US9**: reusa los endpoints de explicación; agrega cards/detalle web
  (T055/T056/T057).
- **US10**: reusa comparación; agrega shortlist (T060/T061) y la matriz
  (T062).
- Trabajo secuencial recomendado: US1 → US2 → US3 → US4 → US5 → US6 → US7 →
  US8 → US9 → (US10 ∥ Polish) → Polish.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Políticas puras antes de servicio; servicio antes de routers; routers antes
  de web.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003/T004/T005 en Setup; T007–T012, T014–T019, T022/T023 en
  Foundational; T025 en US1; T028 en US2; T030/T031 en US3; T033/T034 en US4;
  T036/T037/T038 en US5; T041/T042 en US6; T044/T045 en US7; T049/T050 en US8;
  T054 en US9; T058/T059 en US10; T063/T064/T065/T066 en Polish — tocan
  archivos distintos sin dependencias.
- Tras Foundational, US1/US2/US3 pueden empezar en paralelo (archivos y tests
  separados). Tras US5, US6 y US8 pueden ir en paralelo; US7 sigue a US6 y
  US9 a US7; US10 espera a US8+US9.

---

## Parallel Example: User Story 5

```bash
# Tests de US5 en paralelo:
Task: "Unit tests de publicación atómica en tests/unit/application/scoring/test_run_publish.py"
Task: "Integración del run v1 en tests/integration/scoring/test_run_v1.py"
Task: "Tests del handler extendido en tests/unit/workers/test_run_handler_scoring.py"

# Implementación en paralelo (archivos distintos):
Task: "Publicación atómica en src/umbral/application/scoring/service.py"
Task: "Reemplazo del baseline en src/umbral/application/radar/service.py + workers/radar.py"
```

---

## Implementation Strategy

### MVP First (Critical Path P0 del backlog)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar US1 a US9 en orden (policy → evaluadores → unknown → scoring
   determinista → runs atómicos → explicaciones → API → comparación → web):
   cubren UM-H3-012 a UM-H3-021.
4. **STOP y VALIDAR** cada historia con su Independent Test sobre
   Postgres/PostGIS/pgvector real antes de continuar.
5. Primer recorrido interno del hito completo: US1–US9 con harness y build
   web.
6. Demo/entrega si corresponde; US10 (P1, post primer recorrido) después.

### Incremental Delivery

1. Setup + Foundational → contratos, políticas puras y persistencia listos.
2. US1 → policy versionada → validar → demo (MVP).
3. US2 → evaluadores vía servicio → validar.
4. US3 → semántica unknown vs negativo → validar.
5. US4 → scoring determinista en el run → validar.
6. US5 → runs atómicos con evaluaciones → validar (camino crítico
   UM-H3-012..017).
7. US6 → explicaciones deterministas → validar.
8. US7 → endpoints de explicación → validar.
9. US8 → comparación estructurada → validar.
10. US9 → web de razones/incertidumbre → validar (primer recorrido interno).
11. US10 → comparador persistente → validar (P1).
12. Polish → lineage, harness, evidencia de cierre.

### Parallel Team Strategy

1. Equipo completo Setup + Foundational juntos.
2. Tras Foundational: US1, US2 y US3 en paralelo (archivos y tests separados).
3. Tras US3: US4; luego US5 (deja el run v1 estable).
4. Tras US5: US6 y US8 en paralelo; US7 sigue a US6; US9 sigue a US7.
5. Tras US8+US9: US10; Polish prepara lineage y evidencia.
6. Las historias integran sin romperse entre sí (tablas, repos, routers y
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
- El engine v1 reemplaza al baseline dentro de `recommendation.run`; el
  baseline (`application/radar/scoring.py`) se conserva como referencia para
  los runs legacy y no se usa en runs nuevos.
- No crear un job nuevo: el handler `recommendation.run` se extiende in-place.
- Los endpoints nuevos se registran en `src/umbral/api/main.py` y regeneran el
  cliente TS (`npm run api:generate --workspace @umbral/web`) al publicar sus
  DTOs.
- El comparador (US10) queda detrás de `scoring.comparator_enabled=false`
  hasta el primer recorrido interno del hito.
- Los eventos nuevos son client-side; los serverside existentes
  (`recommendation.run_published.v1`) ya cubren la publicación.
- El copy de explicaciones se revisa con producto según UM-H0-007 antes del
  release (contrato `explanations-v1.json`).
