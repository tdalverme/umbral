# Tasks: Criteria and Observations

**Input**: Design documents from `specs/005-criteria-observations/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice
starts with the failing contract/unit/integration test named here"). En cada
fase se escriben primero los tests indicados y se confirma que fallan por la
conducta ausente antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido
(contratos `criteria/v1`, seed, matcher types, reglas puras, compilación,
puertos, persistencia y migración `0006`). US1 entrega el registry versionado
con invalidación automática; US2 los facts y la compilación; US3 las
observaciones por reglas (handler `extraction.run`); US4 la extracción
cualitativa versionada; US5 la recomputación selectiva (`extraction.recompute`);
US6/US7 los slices P1 (embeddings y contexto urbano) después del primer
recorrido interno.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos machine-checkable de criterios y
extracción, el registry de eventos ampliado, el conjunto golden y los límites
de arquitectura que usarán todas las historias.

- [X] T001 Definir el contrato de conceptos machine-checkable (seed v1:
  `balcon`, `ambientes`, `piso`, `tipo_cocina` por reglas; `luminosidad`,
  `estado_general` por modelo; matcher types registrados con params schema)
  en `contracts/criteria/v1/concepts-seed-v1.json` y
  `contracts/criteria/v1/matcher-types-v1.json`
- [X] T002 [P] Definir el contrato de extracción machine-checkable (input
  permitido por concepto, schema de evidencia `{fragment, span, matched_on}`,
  retry budget, proyección determinista de campos) en
  `contracts/criteria/v1/extraction-v1.json`
- [X] T003 [P] Definir los contratos de compilación y observaciones
  machine-checkable (shape de criterio ejecutable, advertencias,
  confirmaciones soft→hard; identidad de observación, estados y transiciones)
  en `contracts/criteria/v1/compilation-v1.json` y
  `contracts/criteria/v1/observations-v1.json`
- [X] T004 [P] Ampliar el registry cerrado de eventos con los 4 tipos
  `criteria.*` (`concept_version_created.v1`, `compilation_created.v1`,
  `observation_batch_published.v1`, `recompute_completed.v1`; payloads sólo
  ids/versiones/conteos; forbidden: `value`, `fragment`, `description_text`,
  `location_text`, `geometry`) en `contracts/events/v1/events-registry.json`
- [X] T005 [P] Crear el conjunto golden de criterios y observaciones (seed de
  conceptos, matcher types, fragmentos de reglas con valor esperado, facts con
  supersesión, compilaciones incl. soft→hard sin confirmación, eventos
  válidos/inválidos) en `tests/fixtures/criteria/concepts-golden.json`,
  `tests/fixtures/criteria/rules-golden.json`,
  `tests/fixtures/criteria/facts-golden.json`,
  `tests/fixtures/criteria/compilations-golden.json` y
  `tests/fixtures/criteria/events-golden.json` (reusando la fixture Silver
  de 003/004)
- [X] T006 [P] Añadir fixtures de arquitectura para los límites de
  `application/criteria` (permite application→domain y adapters→application;
  prohíbe domain→infrastructure, criteria→FastAPI/LLM directo y dominio con
  imports web) en `tests/architecture/test_criteria_boundaries.py`

**Checkpoint**: contratos publicados, registry de eventos ampliado, conjunto
golden disponible y límites nuevos verificados desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Políticas puras (registry de conceptos, compilación, reglas,
puerto de extracción), puertos y persistencia de las nueve tablas. Nada de las
historias comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T007 Escribir la conformance del concept registry: validación de
  matcher types y params, resolución de alias, colisiones con advertencia en
  `tests/contract/test_concept_registry.py`
- [X] T008 [P] Escribir la conformance de reglas de extracción: casos golden
  de `balcon`, `ambientes`, `piso`, `tipo_cocina` con fragmento de evidencia y
  "sin evidencia" explícito en `tests/contract/test_extraction_rules.py`
- [X] T009 [P] Escribir la conformance de versionado de extracción:
  `extraction_versions` inmutables (kind rule/prompt/schema/model/embedding,
  key, version) en `tests/contract/test_extraction_versions.py`
- [X] T010 [P] Escribir la conformance de compilación: criterio ordenado y
  versionado, advertencias, memoria semántica nunca compilada sin edición,
  soft→hard sin confirmación rechazado en `tests/contract/test_compilation.py`
- [X] T011 [P] Ampliar la conformance del registry de eventos: los 4 tipos
  `criteria.*` con keys requeridas/extra y PII prohibida en
  `tests/contract/test_events_registry.py`
- [X] T012 [P] Escribir los tests de migración `0006` (upgrade desde vacío y
  desde `0005`, head único, drift, downgrade) en
  `tests/migrations/test_0006_criteria_observations.py`
- [X] T013 [P] Escribir los unit tests de repos (índices únicos parciales
  `uq_listing_observations_active`, `uq_listing_embeddings_active`,
  `uq_preference_facts_active`, supersesión `superseded_by`, append-only) en
  `tests/unit/application/criteria/test_repositories.py`

### Implementation for Foundational

- [X] T014 Definir los valores puros y errores (`Concept`, `ConceptVersion`,
  `PreferenceFact`, `Criterion`, `Compilation`, `Observation`,
  `ExtractionVersion`, `RecomputeScope`, `CriteriaError`) en
  `src/umbral/application/criteria/contracts.py`
- [X] T015 [P] Implementar el registry puro de conceptos (loader del seed y
  matcher types, `validate_concept`, `resolve_alias`, colisiones con
  advertencia) en `src/umbral/application/criteria/registry.py`
- [X] T016 [P] Implementar `compile_criteria` puro (perfil + facts activos +
  ediciones + confirmaciones → criterios ordenados, advertencias,
  soft→hard condicionado) en `src/umbral/application/criteria/compile.py`
- [X] T017 [P] Implementar las reglas deterministas de extracción con
  evidencia de fragmento (`balcon`, `ambientes`, `piso`, `tipo_cocina`; "sin
  evidencia" explícito) en `src/umbral/application/criteria/rules.py`
- [X] T018 [P] Implementar el puerto `StructuredExtractor` y la orquestación
  pura (proyección de input permitido desde extraction-v1, validación de
  schema, retry acotado, resultado `ExtractResult`) en
  `src/umbral/application/criteria/extractor.py`
- [X] T019 [P] Definir los puertos `ConceptRepository`, `FactRepository`,
  `CompilationRepository`, `ObservationRepository`, `ExtractionVersionRepository`,
  `RecomputeRunRepository`, `EmbeddingRepository`, `UrbanSignalRepository` en
  `src/umbral/application/criteria/ports.py`
- [X] T020 Implementar los modelos y ENUMs (`fact_state`, `observation_state`,
  `observation_source`, `extraction_kind`, `recompute_scope`,
  `recompute_run_state`) con constraints, índices únicos parciales y
  registrarlos en `src/umbral/infrastructure/db/models/criteria.py` y
  `src/umbral/infrastructure/db/models/__init__.py`
- [X] T021 Crear la revisión `0006_criteria_observations` (down:
  `0005_search_radar`) con las nueve tablas, los ENUMs y los chequeos de
  extensión PostGIS/pgvector en `alembic/versions/0006_criteria_observations.py`
- [X] T022 [P] Implementar los repos SQLAlchemy (sin commit propio, append-only
  con supersesión, índices parciales) en
  `src/umbral/infrastructure/db/repositories/criteria.py`
- [X] T023 [P] Implementar los adapters in-memory para tests en `tests/fakes/criteria.py`
- [X] T024 Añadir los settings `criteria.*` y `extraction.*` (`seed_version`,
  `qualitative_max_attempts` 2, `batch_size` 250, `extraction_job_type`,
  `recompute_job_type`, `provider` fake|managed, `managed_model`,
  `managed_api_key` env-only) más los P1 (`embeddings.enabled` false,
  `embeddings.dimension` 1536, `urban.context_enabled` false) validados al
  iniciar en `src/umbral/infrastructure/config/settings.py` con su test

**Checkpoint**: políticas puras, contratos, persistencia y settings
disponibles y verificados; las historias pueden comenzar.

---

## Phase 3: User Story 1 — Curar la taxonomia de conceptos (Priority: P1) MVP

**Goal**: el registry queda poblado desde el seed versionado y el servicio
permite registrar/editar conceptos con versionado inmutable, invalidación
automática de las observaciones afectadas y evento
`criteria.concept_version_created.v1`.

**Independent Test**: registrar el seed v1 produce `concepts` +
`concept_versions` v1 + evento; una edición crea la versión siguiente sin
mutar la previa; matcher types o params no soportados se rechazan sin
persistir parciales; alias colisionantes advierten y no quedan ambiguos;
una versión nueva de concepto invalida automáticamente sólo las
observaciones activas de ese concepto (SC-001).

### Tests for User Story 1

> Escribir T025–T026 primero y confirmar que fallan por la conducta ausente.

- [X] T025 [P] [US1] Escribir los unit tests de `register_concept_version`
  (persistencia de concepto + versión inmutable + evento
  `criteria.concept_version_created.v1` + invalidación automática de
  observaciones del concepto en la misma transacción) en
  `tests/unit/application/criteria/test_registry_service.py`
- [X] T026 [P] [US1] Escribir los unit tests de validación y alias del
  servicio (matcher type/params inválidos rechazados sin datos parciales;
  colisión de alias con advertencia) en
  `tests/unit/application/criteria/test_registry_service.py`

### Implementation for User Story 1

- [X] T027 [US1] Implementar `register_concept_version` en
  `CriteriaService` (cargar seed al construir, versionar, invalidar
  observaciones afectadas, emitir evento) en
  `src/umbral/application/criteria/service.py`
- [X] T028 [P] [US1] Implementar la composición del servicio de criterios con
  repos SQLAlchemy + registry del seed en
  `src/umbral/infrastructure/criteria/composition.py`

**Checkpoint**: registry versionado verificado por contract conformance +
unit tests sobre repos in-memory; US1 cerrada.

---

## Phase 4: User Story 2 — Declarar preferencias y compilar criterios ejecutables (Priority: P1)

**Goal**: las preferencias se persisten como facts append-only con
supersesión y deny-by-default; `compile_profile` produce el conjunto
ordenado/versionado de criterios ejecutables con advertencias y confirmaciones
registradas, emitiendo `criteria.compilation_created.v1`.

**Independent Test**: una decisión nueva inserta un fact y supersede el
anterior sin mutarlo; a lo sumo un fact activo por (perfil, concepto); hechos
ajenos al usuario rechazados; `compile_criteria` produce el orden y las
advertencias esperadas; memoria semántica nunca compilada sin edición
validada; soft→hard sin confirmación falla o advierte y no convierte (SC-005).

### Tests for User Story 2

> Escribir T029–T030 primero y confirmar que fallan por la conducta ausente.

- [X] T029 [P] [US2] Escribir los unit tests de `record_preference_fact`
  (persistencia de fact con valor/peso/polaridad/confianza/fuente/validez,
  supersesión `superseded_by`, unicidad del fact activo, deny-by-default)
  en `tests/unit/application/criteria/test_facts.py`
- [X] T030 [P] [US2] Escribir los unit tests de `compile_profile`
  (compilación ordenada/versionada por profile version, advertencias,
  confirmaciones soft→hard registradas, evento
  `criteria.compilation_created.v1`) en
  `tests/unit/application/criteria/test_compile_service.py`

### Implementation for User Story 2

- [X] T031 [US2] Implementar `record_preference_fact` (insert + supersede +
  validación de concepto existente) en
  `src/umbral/application/criteria/service.py`
- [X] T032 [P] [US2] Implementar `compile_profile` (persistir compilación por
  (profile_version, compilation_version) + evento) en
  `src/umbral/application/criteria/service.py`

**Checkpoint**: facts y compilaciones verificados por unit tests; US2 cerrada.

---

## Phase 5: User Story 3 — Observar listings con reglas objetivas (Priority: P1)

**Goal**: el job `extraction.run` ejecuta las reglas deterministas sobre el
conjunto de listings y publica observaciones `active` con evidencia de
fragmento, una por (listing, concepto, fuente), emitiendo
`criteria.observation_batch_published.v1`.

**Independent Test**: cada caso golden produce el valor esperado con su
fragmento; doble ejecución produce observaciones idénticas; sin señal
matcheable queda "sin evidencia" explícito; a lo sumo una observación activa
por (listing, concepto, fuente); un reintento del job no duplica observaciones
(SC-002, SC-004, SC-012).

### Tests for User Story 3

> Escribir T033–T034 primero y confirmar que fallan por la conducta ausente.

- [X] T033 [P] [US3] Escribir los unit tests de `process_extraction` para
  fuente `rule` (batch sobre listings, publicar observaciones `active` con
  evidencia y `extraction_version_id`, resumen de conteos) en
  `tests/unit/application/criteria/test_extraction_service.py`
- [X] T034 [P] [US3] Escribir los tests de integración del pipeline de reglas
  (extracción sobre la fixture Silver real, unicidad activa en DB, replay del
  job idempotente) en `tests/integration/criteria/test_extraction_pipeline.py`

### Implementation for User Story 3

- [X] T035 [US3] Implementar `process_extraction` para fuente `rule`
  (selección de listings del scope, ejecutar `run_rule`, publicar observaciones
  con supersesión + evento `criteria.observation_batch_published.v1`) en
  `src/umbral/application/criteria/service.py`
- [X] T036 [P] [US3] Implementar `ExtractionRunHandler` (`extraction.run`) con
  target de scope (`full` o `concept:<key>`), resultado <= 8 KiB y registro en
  el JobRegistry en `src/umbral/workers/criteria.py` y
  `src/umbral/workers/composition.py`

**Checkpoint**: pipeline de reglas verificado sobre Postgres real; US3 cerrada.

---

## Phase 6: User Story 4 — Extraer features cualitativas con salida estructurada versionada (Priority: P1)

**Goal**: la extracción cualitativa corre sobre el puerto `StructuredExtractor`
(proveedor externo gestionado; fake en local/CI), recibe sólo el input
permitido, valida el schema por concepto, reintenta con presupuesto acotado y
persiste observaciones `active`/`failed` con lineage a `extraction_versions`.

**Independent Test**: el extractor envía sólo la proyección permitida (0 PII,
0 raw HTML); outputs válidos persisten `active` con `extraction_version_id`
exacta; outputs inválidos se rechazan o reintentan hasta el máximo y quedan
`failed` con `failure_code` consultable; el modelo nunca decide ranking
(SC-003, SC-013).

### Tests for User Story 4

> Escribir T037–T038 primero y confirmar que fallan por la conducta ausente.

- [X] T037 [P] [US4] Escribir los unit tests del extractor (proyección de
  input permitido desde extraction-v1, validación de schema por concepto,
  reintento acotado, observaciones `failed` con causa) en
  `tests/unit/application/criteria/test_extractor.py`
- [X] T038 [P] [US4] Escribir los unit tests del adapter managed (llamada
  HTTP con input permitido, error transitorio→transient, error permanente→
  `failed`, sin PII en el request) en
  `tests/unit/infrastructure/criteria/test_managed_extractor.py`

### Implementation for User Story 4

- [X] T039 [US4] Implementar el adapter fake de prueba en
  `src/umbral/infrastructure/criteria/extractors/fake.py`
- [X] T040 [P] [US4] Implementar el adapter managed (httpx, modelo y API key
  de settings, proyección permitida, clasificación de errores) en
  `src/umbral/infrastructure/criteria/extractors/managed.py`
- [X] T041 [P] [US4] Implementar la selección de adapter por
  `extraction.provider` en `src/umbral/infrastructure/criteria/composition.py`
- [X] T042 [P] [US4] Implementar `process_extraction` para fuente `model`
  (registrar `extraction_versions` de prompt/schema/modelo, invocar el puerto,
  validar output, persistir `active`/`failed`) en
  `src/umbral/application/criteria/service.py`

**Checkpoint**: extracción cualitativa versionada verificada con fake y
adapter managed testeado con mock; US4 cerrada.

---

## Phase 7: User Story 5 — Recomputar solo lo afectado por un cambio (Priority: P1)

**Goal**: la invalidación es automática al registrarse un cambio de versión
(concepto, prompt/modelo/schema, parser `normalizer_version`); el operador
dispara `extraction.recompute` con scope + causa; la publicación es atómica
y registra `recomputation_runs` con estado/conteos/causa/tiempos.

**Independent Test**: un cambio de versión invalida automáticamente sólo las
observaciones afectadas y deja intactas las demás; el recompute recomputa sólo
el alcance, supersede las invalidadas y publica en una transacción; un job
fallido no deja observaciones a medias ni borra versiones previas; las
invalidadas nunca se usan en resultados nuevos; `recomputation_runs` queda con
conteos y causa (SC-004, SC-009).

### Tests for User Story 5

> Escribir T043–T045 primero y confirmar que fallan por la conducta ausente.

- [X] T043 [P] [US5] Escribir los unit tests de `invalidate_observations`
  (scopes concept/extraction/parser; sólo afectadas cambian; invalidadas
  nunca activas) en `tests/unit/application/criteria/test_invalidation.py`
- [X] T044 [P] [US5] Escribir los tests de integración del recompute (scopes
  sobre DB real, publicación atómica, replay idempotente, fallo inducido sin
  parciales, supersesión correcta) en
  `tests/integration/criteria/test_recompute.py`
- [X] T045 [P] [US5] Escribir los tests de eventos (los 4 tipos `criteria.*`
  escritos en la misma transacción del cambio; forbidden `value`/`fragment`/
  texto rechazado) en `tests/integration/criteria/test_product_events.py`

### Implementation for User Story 5

- [X] T046 [US5] Implementar `invalidate_observations` (auto en
  `register_concept_version` y al registrar una `extraction_versions` nueva;
  scope parser por `normalizer_version`) en
  `src/umbral/application/criteria/service.py`
- [X] T047 [P] [US5] Implementar `submit_recompute` + `process_recompute`
  (persistir `recomputation_runs` con causa, publicar nuevas `active` +
  superseder invalidadas en una transacción + evento
  `criteria.recompute_completed.v1`) en
  `src/umbral/application/criteria/service.py`
- [X] T048 [P] [US5] Implementar `RecomputeHandler` (`extraction.recompute`)
  con target de scope + causa y resultado <= 8 KiB, registrado en
  `src/umbral/workers/criteria.py` y `src/umbral/workers/composition.py`

**Checkpoint**: recomputación selectiva verificada sobre Postgres real;
US5 cerrada. Primer recorrido interno del hito completo.

---

## Phase 8: User Story 6 — Indexar embeddings de listings normalizados (Priority: P1; P1 slice, post primer recorrido)

**Goal**: los embeddings se generan sólo desde la proyección permitida con
versión de modelo registrada (`kind=embedding`), y un cambio de modelo o texto
regenera sólo los afectados conservando las versiones previas
(`embeddings.enabled=false` por default).

**Independent Test**: 100% de embeddings desde la proyección permitida con
modelo/versión registrados; 0 embeddings desde raw HTML o PII; la regeneración
selectiva reemplaza sólo los afectados y preserva versiones previas (SC-007).

### Tests for User Story 6

> Escribir T049–T050 primero y confirmar que fallan por la conducta ausente.

- [X] T049 [P] [US6] Escribir los tests de integración de embeddings
  (generación desde proyección permitida, 0 raw HTML/PII, índice único
  activo, regeneración selectiva con versiones previas preservadas) en
  `tests/integration/criteria/test_embeddings.py`
- [X] T050 [P] [US6] Escribir los unit tests de generación/regeneración de
  embeddings (scope, supersesión, `embeddings.enabled=false` sin efectos) en
  `tests/unit/application/criteria/test_embeddings.py`

### Implementation for User Story 6

- [X] T051 [US6] Implementar la generación y regeneración selectiva de
  embeddings (proyección permitida, `extraction_versions` kind=embedding,
  supersesión por recompute) en `src/umbral/application/criteria/service.py`
- [X] T052 [P] [US6] Implementar el repo SQLAlchemy de `listing_embeddings`
  (vector, índice único parcial activo) en
  `src/umbral/infrastructure/db/repositories/criteria.py`

**Checkpoint**: embeddings P1 verificados; US6 cerrada.

---

## Phase 9: User Story 7 — Incorporar contexto urbano con trazabilidad (Priority: P1; P1 slice, post primer recorrido)

**Goal**: las señales urbanas (cafes, transporte, espacios verdes) se
incorporan con fuente, fecha, geometría y algoritmo, consultas cacheadas con
límites por fuente y respeto de la precisión geográfica autorizada
(`urban.context_enabled=false` por default).

**Independent Test**: el 100% de las señales tiene fuente, fecha, geometría y
algoritmo; consultas repetidas se sirven desde cache respetando los límites;
ninguna señal supera la precisión autorizada del listing (SC-008).

### Tests for User Story 7

> Escribir T053 primero y confirmar que fallan por la conducta ausente.

- [X] T053 [P] [US7] Escribir los tests de integración de contexto urbano
  (persistencia de fuente/fecha/geometría/algoritmo, cache y límites,
  precisión autorizada, `urban.context_enabled=false` sin efectos) en
  `tests/integration/criteria/test_urban_signals.py`

### Implementation for User Story 7

- [X] T054 [US7] Implementar la incorporación de señales urbanas con cache y
  límites por fuente (fuente/fecha/geometría/algoritmo, respeto de
  `geo_precision`) en `src/umbral/application/criteria/service.py`
- [X] T055 [P] [US7] Implementar el repo SQLAlchemy de `urban_signals` y el
  adaptador de cache en `src/umbral/infrastructure/db/repositories/criteria.py`

**Checkpoint**: contexto urbano P1 verificado; US7 cerrada.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: lineage consultable, harness dedicado, evidencia de cierre y gate
completo. Nada de esto cambia el comportamiento de producto.

- [X] T056 Escribir el test de lineage (observación → `extraction_versions` →
  `silver_listings` con `normalizer_version`/`snapshot_id` → snapshot Bronze)
  para el 100% de las observaciones del conjunto de prueba en
  `tests/integration/criteria/test_lineage.py`
- [X] T057 [P] Crear `scripts/check-criteria.ps1` (contract conformance +
  unit + integración criteria sobre testcontainers) y registrarlo en
  `scripts/check.ps1`
- [X] T058 [P] Escribir la evidencia de cierre del incremento en
  `docs/runbooks/evidence/criteria-observations-acceptance.md` (resultado de
  cada SC del spec y recorrido de los escenarios de
  `specs/005-criteria-observations/quickstart.md`)
- [X] T059 [P] Actualizar `docs/runbooks/runtime-local.md` y el quickstart del
  feature con los nuevos jobs (`extraction.run`, `extraction.recompute`) y
  settings
- [X] T060 Verificar el gate completo desde checkout limpio:
  `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`,
  `uv run pytest`, `uv run alembic current --check-heads`, `uv run alembic check`
  y `.\scripts\check.ps1`; documentar el resultado en la evidencia de cierre

---

## Dependencies

- **Setup (Phase 1)**: sin dependencias; publica contratos y fixtures.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P1)**: depende de Foundational; independiente de US2–US7.
- **US2 (P1)**: depende de Foundational; independiente de US1/US3–US7.
- **US3 (P1)**: depende de Foundational; independiente de US1/US2.
- **US4 (P1)**: depende de US3 (`process_extraction` para fuente `rule`,
  T035) y Foundational.
- **US5 (P1)**: depende de US3 y US4 (recompute sobre observaciones de reglas
  y modelo) y Foundational.
- **US6 (P1, slice P1)**: depende de US5 (regeneración selectiva vía recompute).
- **US7 (P1, slice P1)**: depende de Foundational; independiente de US1–US6.
- **Polish (final)**: depende de las historias deseadas (T056/T057/T058/T059
  son paralelizables con las historias tardías).

### User Story Dependencies

- **US1**: `registry.py` (T015) + repos (T022/T023) + `register_concept_version`
  (T027) + composición (T028).
- **US2**: reusa `registry.py`; agrega facts (T031) y `compile_profile` (T032).
- **US3**: reusa `rules.py` (T017) y repos; agrega `process_extraction` (T035)
  y el handler `extraction.run` (T036).
- **US4**: reusa el extractor port (T018); agrega adapters (T039/T040/T041) y
  la rama `model` de `process_extraction` (T042).
- **US5**: reusa `process_extraction`; agrega invalidación (T046),
  submit/process recompute (T047) y el handler `extraction.recompute` (T048).
- **US6**: reusa recompute; agrega embeddings (T051/T052).
- **US7**: reusa Foundational; agrega señales urbanas (T054/T055).
- Trabajo secuencial recomendado: US1 → US2 → US3 → US4 → US5 → (US6 ∥ US7)
  → Polish.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Valores/puertos antes de adapters; adapters antes de servicio; servicio antes
  de handler.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003/T004/T005/T006 en Setup; T008–T013, T015–T019, T022/T023 en
  Foundational; T025/T026 en US1; T029/T030 en US2; T033/T034 en US3;
  T037/T038 en US4; T043/T044/T045 en US5; T049/T050 en US6; T056/T057/T058/T059
  en Polish — tocan archivos distintos sin dependencias.
- US6 y US7 pueden empezar en paralelo una vez que US5 deje la recomputación
  estable (si hay capacidad).

---

## Parallel Example: User Story 5

```bash
# Tests de US5 en paralelo:
Task: "Unit tests de invalidación en tests/unit/application/criteria/test_invalidation.py"
Task: "Integración del recompute en tests/integration/criteria/test_recompute.py"
Task: "Integración de eventos criteria.* en tests/integration/criteria/test_product_events.py"

# Implementación en paralelo (archivos distintos):
Task: "invalidate_observations en src/umbral/application/criteria/service.py"
Task: "submit_recompute + process_recompute en src/umbral/application/criteria/service.py"
Task: "RecomputeHandler en src/umbral/workers/criteria.py + workers/composition.py"
```

---

## Implementation Strategy

### MVP First (Critical Path P0 del backlog)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar US1 a US5 en orden (registry → facts/compilación → reglas →
   cualitativa → recomputación): cubren UM-H3-001 a UM-H3-008 y UM-H3-011.
4. **STOP y VALIDAR** cada historia con su Independent Test sobre
   Postgres/PostGIS/pgvector real antes de continuar.
5. Primer recorrido interno del hito completo: US1–US5 con harness.
6. Demo/entrega si corresponde; US6/US7 (P1, post primer recorrido) después.

### Incremental Delivery

1. Setup + Foundational → contratos, políticas puras y persistencia listos.
2. US1 → registry versionado → validar → demo (MVP).
3. US2 → facts y compilación → validar.
4. US3 → observaciones por reglas → validar.
5. US4 → extracción cualitativa versionada → validar.
6. US5 → recomputación selectiva → validar (primer recorrido interno).
7. US6 → embeddings indexados → validar.
8. US7 → contexto urbano → validar.
9. Polish → lineage, harness, evidencia de cierre.

### Parallel Team Strategy

1. Equipo completo Setup + Foundational juntos.
2. Tras Foundational: US1 y US2 en paralelo (archivos y tests separados);
   US3 puede empezar tras dejar el pipeline de reglas estable.
3. Tras US3: US4 en paralelo con los primeros casos de recompute de US5.
4. Tras US5: US6 y US7 en paralelo; Polish prepara lineage y evidencia.
5. Las historias integran sin romperse entre sí (tablas, repos y jobs
   separados; el registry de eventos crece aditivamente).

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
- Este incremento no toca HTTP/OpenAPI/policy/web (FR-024): no regenerar
  cliente, no cambiar `domain/identity/policy.py`.
- No agregar dependencias de Python nuevas (pgvector y httpx ya existen).
- Los jobs nuevos (`extraction.run`, `extraction.recompute`) se registran en
  `workers/registry.py`/`workers/composition.py` y se documentan en
  `docs/runbooks/runtime-local.md`.
