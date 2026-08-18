# Tasks: Señales urbanas declarativas

**Input**: Design documents from `specs/017-urban-signals/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: La feature exige verificaciones automatizadas en cada slice:
conformance del contrato, golden del calculator, integration sobre PostGIS con
snapshot fixture, y trayectorias de puente. En cada historia se escriben
primero los tests indicados y se confirma que fallen por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido; las
integraciones transversales permanecen explícitas en US3 (expansibilidad) y en
el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Crear el layout del módulo urbano, la migración del esquema y el
registro del contrato, sin comportamiento de producto.

- [X] T001 Crear los paquetes vacíos aprobados `src/umbral/application/urban/__init__.py`, `src/umbral/infrastructure/urban/__init__.py` y `src/umbral/ops/urban.py`
- [X] T002 [P] Copiar el contrato publicado a `contracts/urban/v1/urban-contract-v1.json` (idéntico a `specs/017-urban-signals/contracts/urban-contract-v1.json`)
- [X] T003 Crear la migración `alembic/versions/0017_urban_signals.py`: tablas `urban_contracts`, `urban_snapshots`, `urban_categories`, `urban_primitives`, `urban_signals`, `neighborhood_signal_stats`, reemplazo de la tabla urbana actual, y `listing_observations` sin cambios estructurales
- [X] T004 [P] Registrar el contrato `urban-contract-v1` como `extraction_version` (`kind=urban`, `artifact_version=urban-contract-v1`) en el seed de versiones de extracción existente
- [X] T005 Actualizar `tests/migrations/test_upgrade_and_drift.py` con el head `0017_urban_signals` y escribir `tests/migrations/test_0017_urban_signals.py` (upgrade/downgrade con datos urbanos)

**Checkpoint**: la migración corre de punta a punta contra Postgres real y el
head del árbol es 0017.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establecer el contrato ejecutable, el calculator puro y el matcher
que usarán todas las historias.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

- [X] T006 Escribir conformance del contrato en `tests/contract/test_urban_contract.py`: estructura, refs de primitivas, pesos normalizados, params por op, modos de normalización, sin ciclos en compuestas, atribución y licencia obligatorias
- [X] T007 Escribir loader/parser del contrato en `src/umbral/application/urban/contract.py` que valide el JSON y exponga `UrbanContract` tipado
- [X] T008 Escribir golden del calculator en `tests/unit/application/urban/test_calculator.py`: primitivas de ejemplo → señales exactas esperadas (crudo), incluyendo densidad, distancia, missing parcial y neutral
- [X] T009 Implementar el calculator puro en `src/umbral/application/urban/calculator.py` que ejecuta el contrato (dos niveles: base y compuestas, orden topológico, op count/distance, clamp 0-1)
- [X] T010 Implementar la confidence declarada (`weighted_input_coverage` + `missing_penalty`) en `src/umbral/application/urban/confidence.py`
- [X] T011 Declarar el matcher `signal_score` en el registry de matchers y su evaluador puro en `src/umbral/application/scoring/evaluators.py`, con tests en `tests/unit/application/scoring/test_signal_score.py`
- [X] T012 Migrar los concepts `proximidad_cafes` y `acceso_transporte` de `proxy` a `signal_ref` (`cafe_lifestyle`, `transit_access`) y `matcher_type=signal_score` en `contracts/criteria/v1/concepts-seed-v1.json`, actualizando sus tests de conformance

**Checkpoint**: el contrato valida, el calculator produce señales exactas, el
matcher traspasa scores y los concepts migran sin romper el scoring.

---

## Phase 3: User Story 1 - Preferencias de entorno expresadas naturalmente (Priority: P1) MVP

**Goal**: Un listing con coordenadas precisas obtiene señales urbanas
factuales, que se entregan como observaciones al scoring con score,
confidence y evidencia; sin datos, la preferencia se conserva con
desconocimiento explícito.

**Independent Test**: un listing con coordenadas precisas y snapshot
importado recibe observaciones urbanas con score, confidence y contributors;
un listing sin coordenadas no tiene señales y su preferencia urbana se reporta
como dato faltante (no valor medio).

### Tests for User Story 1

> Escribir T013–T016 primero y confirmar que fallan por la conducta ausente.

- [X] T013 [P] [US1] Escribir tests del repo urbano en `tests/integration/urban/test_repository.py`: snapshot, categorías, primitivas, señales y stats sobre PostGIS
- [X] T014 [P] [US1] Escribir tests del extractor de observaciones urbanas en `tests/unit/application/urban/test_observations.py`: concept con `signal_ref` produce observación con score/confidence/evidence; sin señal produce `missing`
- [X] T015 [P] [US1] Escribir tests del flujo "listing sin coordenadas → excluido, preferencia como dato faltante" en `tests/unit/application/urban/test_exclusion.py`
- [X] T016 [P] [US1] Escribir tests del worker de batch en `tests/integration/urban/test_batch_worker.py`: distancias → señales → stats → observaciones sobre PostGIS

### Implementation for User Story 1

- [X] T017 [US1] Implementar repos urbanos SQLAlchemy en `src/umbral/infrastructure/db/repositories/urban.py` (snapshots, categorías, primitivas, señales, stats) y exponerlos en `src/umbral/infrastructure/db/repositories/__init__.py`
- [X] T018 [P] [US1] Implementar el cálculo de distancias por listing (ST_DWithin, radio del contrato) en `src/umbral/infrastructure/urban/distance_calculator.py`
- [X] T019 [US1] Implementar la normalización por barrio (percentiles + fallback global decidido en el job) en `src/umbral/application/urban/normalization.py`
- [X] T020 [US1] Implementar el worker de batch en `src/umbral/workers/urban.py`: primitivas → señales crudas → stats por barrio → normalización → observaciones, registrado en el registry de workers
- [X] T021 [P] [US1] Implementar el extractor de observaciones urbanas en `src/umbral/application/urban/observations.py` (concept `signal_ref` → `ListingObservation` con `source=urban`, `matcher_type=signal_score`, evidence=contributors)
- [X] T022 [US1] Integrar el matcher `signal_score` en el despacho del engine de scoring y verificar que las observaciones urbanas puntúan sin cambios de política

**Checkpoint**: los tests T013–T016 pasan; el batch produce observaciones
para listings con coordenadas y `missing` honesto para el resto.

---

## Phase 4: User Story 2 - Comparación justa entre barrios (Priority: P1)

**Goal**: Las señales de densidad se comparan contra el barrio; las de
distancia a infraestructura mayor permanecen absolutas; el fallback global es
estable y la explicación declara el alcance.

**Independent Test**: dos listings con la misma densidad cruda en barrios de
cobertura distinta obtienen señales normalizadas comparables en su contexto, y
la explicación declara el alcance de comparación.

### Tests for User Story 2

> Escribir T023–T025 primero y confirmar que fallan por la conducta ausente.

- [X] T023 [P] [US2] Escribir tests de normalización en `tests/unit/application/urban/test_normalization.py`: percentil por barrio, modo por señal, min_sample y fallback global
- [X] T024 [P] [US2] Escribir tests de la tabla de stats en `tests/integration/urban/test_neighborhood_stats.py`: recálculo en el job, `normalization_scope` estable entre batches
- [X] T025 [P] [US2] Escribir tests de explicación en `tests/unit/application/urban/test_explanations.py`: alcance ("tu barrio"/"toda la ciudad"), datos crudos, sin mención de la fuente

### Implementation for User Story 2

- [X] T026 [US2] Implementar el cálculo de percentiles por barrio y señal en `src/umbral/application/urban/normalization.py` (completar si T019 lo dejó parcial)
- [X] T027 [US2] Exponer `normalization_scope` y `sample_size` en el payload de observación para las explicaciones en `src/umbral/application/urban/observations.py`
- [X] T028 [P] [US2] Incluir el alcance de comparación y los datos crudos en la explicación de la señal en `src/umbral/application/scoring/explanations.py`

**Checkpoint**: los tests T023–T025 pasan; la comparación entre barrios es
justa y la explicación declara el alcance.

---

## Phase 5: User Story 3 - Agregar una señal nueva sin tocar el ranking (Priority: P2)

**Goal**: Una señal nueva declarada en el contrato se computa, persiste y se
expone sin cambios de código en el scoring ni en los workers de criterios;
cambiar el contrato invalida las observaciones previas y fuerza recálculo.

**Independent Test**: una señal nueva declarada en el contrato se computa en
el batch siguiente y se expone, sin tocar código de scoring ni de workers.

### Tests for User Story 3

> Escribir T029–T031 primero y confirmar que fallan por la conducta ausente.

- [X] T029 [P] [US3] Escribir test de contrato: agregar una señal/categoría nueva y verificar que el parser la acepta sin cambios de código en `tests/contract/test_urban_contract.py`
- [X] T030 [P] [US3] Escribir test de invalidez: cambiar la versión del contrato supersede las observaciones previas en `tests/integration/urban/test_contract_invalidation.py`
- [X] T031 [P] [US3] Escribir test de recálculo: snapshot reimportado recalcula el 100% de los listings con coordenadas y ninguno conserva señales viejas en `tests/integration/urban/test_reimport.py`

### Implementation for User Story 3

- [X] T032 [US3] Implementar el ciclo de vida del contrato: registrar versión nueva, superseder la anterior y marcar observaciones fuera de vigencia en `src/umbral/application/urban/contract.py` y `src/umbral/infrastructure/db/repositories/urban.py`
- [X] T033 [US3] Implementar el reimport de snapshot: hash y fecha, verificación contra el snapshot activo, y disparo del recálculo completo en `src/umbral/workers/urban.py`
- [X] T034 [P] [US3] Exponer las señales disponibles (contrato + snapshot vigente) para inspección en `src/umbral/api/routers/urban.py`

**Checkpoint**: los tests T029–T031 pasan; agregar una señal es editar JSON y
reimportar; las observaciones viejas nunca se muestran como vigentes.

---

## Phase 6: User Story 4 - Datos urbanos auditables y licenciados (Priority: P2)

**Goal**: El comando de ops importa el snapshot (descarga externa → object
storage → import), cada observación traza a su contrato y snapshot, y la
atribución de OpenStreetMap es visible en una superficie global.

**Independent Test**: cada observación urbana permite trazar su snapshot
(fuente, fecha, hash) y la aplicación muestra la atribución en una superficie
global.

### Tests for User Story 4

> Escribir T035–T037 primero y confirmar que fallan por la conducta ausente.

- [X] T035 [P] [US4] Escribir tests del comando de ops en `tests/unit/ops/test_import_urban.py`: descarga externa, verificación de hash, subida a object storage e import sin red en el worker
- [X] T036 [P] [US4] Escribir tests de trazabilidad en `tests/integration/urban/test_lineage.py`: observación → contrato → snapshot (fuente, fecha, hash)
- [X] T037 [P] [US4] Escribir tests de atribución en `apps/web/src/app/runtime-routes.test.ts`: la superficie global muestra la atribución de OpenStreetMap

### Implementation for User Story 4

- [X] T038 [US4] Implementar el comando de ops `python -m umbral.ops.import_urban --fetch --import` en `src/umbral/ops/urban.py`: descarga desde Geofabrik, hash SHA-256, subida a object storage, invocación del worker de import
- [X] T039 [US4] Implementar el importador osmium en `src/umbral/infrastructure/urban/osm_importer.py`: parseo de nodos/ways, clasificación por `tags_mapping`/`linear_tags_mapping`, persistencia en categorías
- [X] T040 [P] [US4] Exponer `attribution` y `license` del contrato en el endpoint de señales en `src/umbral/api/routers/urban.py`
- [X] T041 [P] [US4] Mostrar la atribución de OpenStreetMap en una superficie global del frontend (footer o página de licencias) en `apps/web/src/components/`
- [X] T042 [US4] Registrar el run del import en el job runtime (auditable) en `src/umbral/workers/urban.py` y el evento de import en el registry de eventos

**Checkpoint**: los tests T035–T037 pasan; el comando de ops es reproducible y
auditable; la atribución es visible.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cerrar el puente conversacional, la integración con el harness y
la documentación de la feature.

- [X] T043 Agregar el caso de puente en trayectorias: seedear una observación urbana y verificar que "quiero estar cerca de cafes" se vincula a `cafe_lifestyle` (no `unresolved`) con contribución no cero en `tests/integration/agent_evals/test_trajectories_v2.py` y `contracts/agent-evals/v2/conversation-trajectories-v2.json`
- [X] T044 Integrar el check urbano en el harness `scripts/check.ps1` y crear `scripts/check-urban.ps1` con conformance, unit, integration y trayectorias
- [X] T045 [P] Documentar la operación del snapshot y el comando de ops en `docs/ops/urban-signals.md` (descarga, verificación, reimport, recálculo)
- [X] T046 [P] Documentar la feature en `docs/api/endpoints.md` (endpoint de señales) y actualizar `CONTEXT.md` con el vocabulario urbano
- [X] T047 Actualizar el checklist `specs/017-urban-signals/checklists/requirements.md` marcando la validación de la implementación

**Checkpoint**: el harness completo pasa (incluyendo trayectorias con el caso
de puente) y la documentación operativa cubre el ciclo del snapshot.

---

## Dependencies & Parallel Execution

**User Story completion order**:

```text
US1 ──► US2 ──► US3 ──► US4 ──► Polish
```

- US1 depende de Foundational (T006–T012).
- US2 depende de US1 (la normalización usa señales crudas de US1).
- US3 depende de US2 (el recálculo usa la normalización).
- US4 es independiente de US2/US3 para el comando de ops (T038–T039), pero
  comparte el importador con US3 (reimport). US4 puede arrancar en paralelo
  con US2 usando T038/T039 si T019 (normalización) ya está completado.

**Parallel opportunities**:

- Dentro de cada fase: todos los tasks `[P]` (tests y archivos independientes).
- Fase US1: T013–T016 en paralelo; T017–T022 secuenciales salvo T018/T021.
- Fase US4: T035–T037 en paralelo; T038→T039→T042 secuenciales.

**Implementation strategy (MVP first)**:

- **MVP = US1**: contrato ejecutable, calculator, matcher, repos, batch y
  observaciones con `missing` honesto. Es el slice que valida el quickstart
  Escenario 1 y 2.
- **Siguiente incremento**: US2 (normalización justa) + US4 (ops/atribución).
- **Último**: US3 (expansibilidad) + Polish (puente conversacional, harness,
  docs).
