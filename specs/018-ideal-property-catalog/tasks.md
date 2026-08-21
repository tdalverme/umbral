# Tasks: Catalogo del inmueble ideal con fuerza por usuario

**Input**: Design documents from `specs/018-ideal-property-catalog/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: La feature exige verificaciones automatizadas en cada slice:
conformance de los contratos v2, golden de extraccion, tests de engine
(hard/soft), trayectorias de bridge y regresion de matching. En cada historia
se escriben primero los tests indicados y se confirma que fallen por la
conducta ausente antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen solo trabajo compartido;
las integraciones transversales permanecen explicitas en US2/US3 y en el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Crear los contratos v2 y su carga activa, manteniendo v1 intacto
para los tests de conformance existentes.

- [X] T001 Crear `contracts/criteria/v2/concepts-seed-v2.json` con los conceptos de vivienda (`dormitorios`, `banos`, `mascotas`, `amoblado`, `ascensor`, `cochera`, `piscina`) y urbanos (`acceso_escuela`, `acceso_deporte`, `acceso_cultura`, `acceso_bici`, `acceso_salud`) segun `data-model.md`/`contracts/catalog-hardsoft-contracts.md`; `contract_version: "2"`, `seed_version: "concepts-v2"`
- [X] T002 Crear `contracts/criteria/v2/extraction-v2.json` que agrega `bedrooms` a `allowed_input_fields` y declara por concepto source/input_fields/schema (dormitorios=rule, banos=model, mascotas=rule, amoblado=model, ascensor/cochera/piscina=rule, urbanos=urban)
- [X] T003 Crear `contracts/criteria/v2/extraction-goldens-v2.json` (o extender patron v1) con goldens por concepto nuevo: `dormitorios` (regla desde bedrooms), `mascotas` (positivo/negativo), `ascensor` (amenity), etc.
- [X] T004 Crear `contracts/urban/v2/urban-contract-v2.json` con categorias nuevas (school, sport_pitch+gym, cinema/library/theatre+museum, cycleway+bicycle_parking), primitivas y senales nuevas (`school_access`, `sport_access`, `culture_access`, `bike_access`, `health_access`)
- [X] T005 Actualizar `src/umbral/infrastructure/criteria/contract_loader.py` para cargar v2 como contrato activo (falta `load_concepts_seed_v2`, `load_extraction_contract_v2`, `load_extraction_goldens_v2` o un parametro de version) sin romper `load_*` v1
- [X] T006 Crear `tests/migrations/test_0018_hard_soft_catalog.py` (e ignorar/saltar si no hay migracion nueva requerida; documentar por que) y registrar head en `tests/migrations/test_upgrade_and_drift.py` si aplica
- [X] T007 Actualizar `tests/conftest`/fixtures del criteria test context para cargar v2 como catalogo por defecto de los tests nuevos (manteniendo v1 para los tests legacy de shape)

**Checkpoint**: `pytest tests/contract/test_concept_registry.py tests/contract/test_urban_contract.py` pasan (v1 intacto) y la carga de v2 devuelve el catalogo nuevo sin errores.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establecer las reglas deterministas, el schema de extraccion difusa
y el puente entre concepts urbanos y senales v2.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

- [X] T008 [P] Escribir conformance de `concepts-seed-v2.json` en `tests/contract/test_concept_registry_v2.py`: el catalogo activo carga, todos los matcher/types validos, params dentro de matcher-types, sin alias colision
- [X] T009 [P] Escribir golden de extraccion para los conceptos de regla en `tests/contract/test_extraction_goldens_v2.py` (dormitorios/ascensor/cochera/piscina/mascotas) sobre `extraction-goldens-v2.json`
- [X] T010 [P] Escribir test de conformance de `urban-contract-v2.json` en `tests/contract/test_urban_contract_v2.py`: categorias nuevas existentes, senales declaradas, pesos normalizados, sin ciclos
- [X] T011 Implementar reglas deterministas en `src/umbral/application/criteria/rules.py`: `run_dormitorios` (lea `bedrooms` estructurado), `run_mascotas` (positivo/negativo), `run_ascensor`, `run_cochera`, `run_piscina` (mapeo desde `amenities`), registradas en `RULE_RUNNERS`
- [X] T012 Agregar schema de modelo para `banos` y `amoblado` en `extraction-v2.json` (value, evidence, confidence, enum para amoblado) y validar contra `validate_model_output`
- [X] T013 En `src/umbral/infrastructure/urban/composition.py`, `_signal_ref_concepts` ya es generico; verificar que los 5 signal_ref nuevos se resuelven contra el catalogo activo y agregar `health_access` si no esta
- [X] T014 Actualizar tests de set exacto que ahora cambian: `tests/contract/test_concept_registry.py`, `tests/unit/application/criteria/test_registry_service.py`, `tests/unit/application/criteria/test_extraction_service.py`, `tests/unit/application/criteria/test_invalidation.py` y `tests/contract/test_extraction_rules.py` para reflejar el catalogo v2 (atomicamente con T011)

**Checkpoint**: las reglas nuevas extraen con evidencia/fragmento; el catalogo v2 valida; los urbanos v2 se resuelven; los tests legacy de set se actualizaron sin romper el estado.

---

## Phase 3: User Story 1 - Describir la vivienda ideal con conceptos que ya existen (Priority: P1) MVP

**Goal**: Una persona expresando "2 dormitorios, aceptan mascotas, con ascensor" produce hechos computables con evidencia; la extraccion es determinista donde hay dato estructurado y honesta donde no.

**Independent Test**: un listing con `bedrooms=2` y amenities que incluyen "ascensor" produce observaciones activas `dormitorios=2` y `ascensor=true` con fragmento/amenity de evidencia; un listing sin dato produce `unknown` y no inventa valor.

### Tests for User Story 1

> Escribir T015–T017 primero y confirmar que fallan por la conducta ausente.

- [X] T015 [P] [US1] Escribir tests de reglas en `tests/unit/application/criteria/test_rules_v2.py`: dormitorios desde bedrooms (y fallback descripcion), mascotas positivo/negativo, amenities booleanos con evidencia `matched_on`
- [ ] T016 [P] [US1] Escribir tests de schema de modelo en `tests/unit/application/criteria/test_extractor_model_v2.py`: `banos`/`amoblado` validan contra schema, evidencia requerida, enums respetados
- [ ] T017 [P] [US1] Escribir test de puente end-to-end en `tests/integration/criteria/test_catalog_v2_pipeline.py`: seed v2 + process_extraction(full) produce observaciones activas para los conceptos nuevos

### Implementation for User Story 1

- [ ] T018 [US1] Registrar en `seed-local.py` el catalogo v2 (concepts/extraction/goldens) para el seed local y el ciclo de observaciones
- [X] T019 [US1] Verificar el ciclo de observaciones: `service.py` produce `ListingObservation` para los conceptos nuevos con `source=rule/model` y estado activo; fragmento de evidencia presente
- [X] T020 [US1] Agregar entradas de vocabulario de preferencias para los conceptos nuevos en `contracts/criteria/v1/preferences-vocabulary-v1.json` (o version nueva) para que el copiloto los proponga; respetar invariante vocab->concept de `tests/contract/test_preferences_vocabulary.py`

**Checkpoint**: los tests T015–T017 pasan; seed local produce observaciones activas para los 7 conceptos de vivienda.

---

## Phase 4: User Story 2 - Describir el entorno con senales urbanas nuevas (Priority: P1)

**Goal**: Un listing con coordenadas precisas obtiene las 5 senales urbanas nuevas como observaciones con score/confidence/contributors; sin datos, la preferencia queda desconocida de forma honesta.

**Independent Test**: dos listings en barrios distintos computan `school_access`/`health_access` comparables por barrio con fallback global cuando la muestra es baja; el `missing` nunca se muestra como valor medio.

### Tests for User Story 2

> Escribir T021–T023 primero y confirmar que fallen por la conducta ausente.

- [ ] T021 [P] [US2] Escribir test del batch urbano con contrato v2 en `tests/integration/urban/test_batch_worker_v2.py`: categorias v2 -> primitivas -> senales v2 -> observaciones sobre PostGIS
- [ ] T022 [P] [US2] Escribir test de observaciones urbanas v2 en `tests/unit/application/urban/test_observations_v2.py`: concept con signal_ref nuevo produce observacion con evidence=contributors; sin senal produce `missing`
- [ ] T023 [P] [US2] Escribir test de normalizacion/degradacion en `tests/unit/application/urban/test_normalization_v2.py`: senales con muestra baja caen a fallback CABA con confianza x0.7; sin referencia quedan percentil 0.5 (desconocido-no-cero)

### Implementation for User Story 2

- [ ] T024 [US2] Asegurar que `urban.contract v2` se registra como `extraction_version` (`kind=urban`, `artifact_version=urban-contract-v2`) y que el batch invalida/publica observaciones urbanas al cambiar de contrato
- [ ] T025 [US2] Hacer correr el batch urbano sobre v2 en `src/umbral/workers/urban.py` (sin cambio de codigo si el pipeline es contract-driven; verificar `_signal_ref_concepts` y `urban.batch`)

**Checkpoint**: los tests T021–T023 pasan; el batch produce las 5 senales v2 y los `missing` son honestos, sin tocar scoring.

---

## Phase 5: User Story 3 - Que cualquier criterio sea soft o hard por usuario (Priority: P1)

**Goal**: Un criterio estructurado se expresa como soft (ordena) o hard (excluye) por usuario, con produccion desde el copiloto (mode), confirmacion (HardConfirmationRef), propagacion del compilador y exclusion del engine en mismatch; semantico nunca hard.

**Independent Test**: con confirmacion, un criterio hard excluye los candidatos en mismatch; sin confirmacion, `SoftToHardRequiresConfirmation` que bloquea; una señal hard con umbral excluye bajo el umbral; un semantico no se eleva.

### Tests for User Story 3

> Escribir T026–T029 primero y confirmar que fallen por la conducta ausente.

- [X] T026 [P] [US3] Escribir test de compilacion hard/soft en `tests/contract/test_compilation_v2.py`: binding/fact con mode hard -> `CompiledCriterion.soft_to_hard=True` solo con confirmacion; semantico rechazado; threshold de señal validado
- [X] T027 [P] [US3] Escribir test de engine en `tests/unit/application/scoring/test_hard_soft.py`: criterio hard + resultado mismatch => candidato excluido; soft => solo reordenamiento; señal hard con umbral => exclusion
- [ ] T028 [P] [US3] Escribir test de policy en `tests/unit/application/scoring/test_policy_hard_soft.py`: `soft_to_hard` con semantico no permitido; pesos/gates intactos
- [X] T029 [P] [US3] Escribir test de golden dataset en `tests/unit/application/matching/test_golden_v2.py`: `HardFilterOutcome` soporta `excluded_criterion:<concept>` y los casos de mascotas/señal hard pasan; regresion `filter_mismatch` declarada

### Implementation for User Story 3

- [ ] T030 [US3] Implementar produccion de mode en `src/umbral/application/preferences/service.py` / interpretacion: `record_expression`/`revise_expression` aceptan `BindingDraft.mode` y aplican `_validate_drafts`/`validate_binding` para exigir `HardConfirmationRef` cuando `mode=hard`
- [X] T031 [US3] Implementar en `src/umbral/application/preferences/policy.py` (o `service.py`) la regla: los semánticos nunca admiten hard (`binding.mode` forzado/validado a soft para `kind=semantic`)
- [X] T032 [US3] Implementar en `src/umbral/application/criteria/compile.py`: mapear el `mode`/`soft_to_hard` del binding al `CompiledCriterion.soft_to_hard`, robusteciendo `_facts_to_criteria` y exigiendo la confirmacion ya existente (`SoftToHardRequiresConfirmation`); propagar `params.threshold` para signals hard
- [X] T033 [US3] Implementar exclusion en `src/umbral/application/scoring/engine.py`: un criterio compilado con `soft_to_hard=True` y `result.state == "mismatch"` excluye al candidato (mismo camino que `gate=="exclude_on_mismatch"`); en `evaluators.py` aplicar el umbral percentil para `signal_score`
- [X] T034 [US3] Agregar el outcome nuevo a `src/umbral/application/matching/contracts.py`/`golden.py`/`regression.py` (HardFilterOutcome + `_single_outcome` + `filter_mismatch`) y documento en `contracts/matching/v1/releases-v1.json` (release con cambio declarado)
- [X] T035 [US3] Registrar evento de elevacion (`preference.hard_elevated`) en el registry de eventos y exceder/superar hipotesis del mismo concepto con trazabilidad (FR-012/FR-013) en el servicio de feedback/proposals

**Checkpoint**: los tests T026–T029 pasan; el hard excluye deterministamente; el semantico no se eleva; la regresion de matching esta declarada.

---

## Phase 6: User Story 4 - Entender que se entendio y que no (Priority: P2)

**Goal**: Un deseo no evaluable se conserva y el copiloto explica el limite + sugiere un puente; los radares vacios por hard persisten diagnostics con relajaciones sugeridas y evento.

**Independent Test**: un deseo no computable ("buena onda") queda con explicacion de limite y un puente sugerido; un hard que vacia candidatos produce diagnostics (relajaciones) + evento, nunca un vacio silencioso.

### Tests for User Story 4

> Escribir T036–T038 primero y confirmar que fallen por la conducta ausente.

- [ ] T036 [P] [US4] Escribir test del puente no-evaluable en `tests/unit/application/conversation/test_unmapped_bridge.py`: deseo sin concepto -> explicacion de limite + sugerencia de concepto cercano, conservando la expresion
- [X] T037 [P] [US4] Escribir test de diagnostics de vacio por hard en `tests/unit/application/radar/test_diagnostics_v2.py`: set vacio con criterio hard responsable -> exclusion_counts por concepto + relajaciones sugeridas + evento auditable
- [X] T038 [P] [US4] Escribir test de evento/hipotesis en `tests/unit/application/feedback/test_hard_elevation.py`: al elevar a hard se emite `preference.hard_elevated` y las hipotesis del concepto quedan superadas

### Implementation for User Story 4

- [ ] T039 [US4] Implementar el puente en la respuesta del copiloto (graph/planificador): detects deseos sin concepto y emite explicacion + sugerencia de concepto evaluable cercano usando el vocabulario (sin escribir preferencia dura)
- [X] T040 [US4] Implementar en `src/umbral/application/radar/diagnostics.py` la identificacion del criterio hard responsable del vacio y la relajacion sugerida correspondiente; persistir diagnostics + evento en el servicio de radar

**Checkpoint**: los tests T036–T038 pasan; cero radares vacios silenciosos; el deseo no-evaluable queda con puente honesto.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cerrar las trayectorias (medicion de mapeo), la regresion de matching, el harness y la documentacion.

- [ ] T041 Agregar trayectorias de bridge en `contracts/agent-evals/v2/conversation-trajectories-v2.json` (o version ad-hoc): una por cluster (vivienda: "2 dormitorios", "acepta mascotas"; urbano: "cerca de una escuela") verificando que se vinculan al concepto correspondiente (no `unresolved`) con fact computable y, para la metrica, un umbral de tasa de mapeo >=80% en el harness
- [X] T042 Ejecutar la regresion de matching (`tests/unit/application/matching/`) y confirmar que la declaracion de la release de golden dataset cubre el cambio de rankings producido por las senales v2 (sin errores `unknown_change`)
- [X] T043 Integrar los nuevos checks en el harness: crear `scripts/check-catalog.ps1` (o extender check.ps1) con conformance v2 + unit (rules/engine/preferences/radar) + integracion (criteria/urban) + matching v2
- [ ] T044 [P] Actualizar `docs/api/endpoints.md` con conceptos/senales nuevas y `docs/ops/urban-signals.md` con el contrato v2 (reimport)
- [X] T045 [P] Actualizar `CONTEXT.md` con los conceptos/senales nuevos y la semantica de "modo de fuerza" (soft/hard por radar), asi como `docs/architecture/overview.md`
- [X] T046 Actualizar el checklist `specs/018-ideal-property-catalog/checklists/requirements.md` marcando la validacion de la implementacion

**Checkpoint**: el harness completo pasa (incluidas trayectorias de bridge y regresion de matching declarada); la documentacion cubre el catalogo v2 y el modo de fuerza.

---

## Dependencies & Parallel Execution

**User Story completion order**:

```text
US1 ──► US2 ──► US3 ──► US4 ──► Polish
```

- US1 depende de Foundational (T008–T014).
- US2 depende de Foundational (contrato v2) y comparte el catalogo con US1 pero es independiente de las reglas; puede arrancar en paralelo con US1 usando T004/T010.
- US3 depende de US1/US2 para tener conceptos que elevar, y de Foundational (compilacion/confirmacion).
- US4 depende de US3 (los vacios por hard son su caso principal) pero el puente no-evaluable puede arrancar antes.
- Polish depende de todas.

**Parallel opportunities**:

- Dentro de cada fase: todos los tasks `[P]` (tests y archivos independientes).
- Fase Foundational: T008/T009/T010 en paralelo; T011→T014 secuenciales (T014 actualiza set exacto con T011).
- Fase US2: T021–T023 en paralelo; T024→T025 secuenciales.
- Fase US3: T026–T029 en paralelo; T030→T035 secuenciales.

**Implementation strategy (MVP first)**:

- **MVP = US1 + US3**: catalogo de vivienda con extraccion determinista + hard/soft sobre conceptos estructurados. Es el slice que valida el quickstart Escenario 1 y 3 (el corazon de la spec: descripcion del inmueble ideal y fuerza por usuario).
- **Siguiente incremento**: US2 (senales urbanas v2) + US4 (puente/diagnostics).
- **Ultimo**: Polish (trayectorias de mapeo, regresion de matching, harness, docs).
---

## Estado de implementacion (2026-08-19)

**Verificado en este entorno** (pytest unit+contract = 1195 passed; ruff, mypy, check-docs, check-architecture en verde):

- Contracts v2 creados y parseados (31 conceptos, 13 senales urbanas); loader activo apunta a v2 (T001-T005, T008-T010).
- Reglas deterministas nuevas con goldens y tests (T011, T015).
- Compilacion propagara soft_to_hard desde facts con confirmacion; semantico nunca hard (T032, T031).
- Engine excluye en mismatch para hard dentro y fuera del policy; umbral de senal respetado (T033, T027).
- Supersesion de hipotesis + evento preference.hard_elevated.v1 (T035, T038).
- Diagnostics reporta criterios hard por concepto (T040, T037).
- Migracion 0018 validada en Postgres real (upgrade/downgrade) + head actualizado (T006).
- Harness criteria extendido; regresion matching sin error (T042, T043).

**Pendiente** (requiere testcontainers/Postgres CI o trabajo conversacional, documentado en checklists/requirements.md):

- Tests de integracion US2 sobre PostGIS (T021-T025): el pipeline es contract-driven y el loader ya apunta a v2; falta la corrida de integracion local.
- Test de puente end-to-end US1 y produccion real de mode desde el copiloto (T030, T016, T017): el seam esta listo y verificado en dominio; el LLM-interpreter aun no emite mode=hard.
- Trayectorias de bridge para medir la tasa de mapeo (T041).
- Puente no-evaluable en el graph del copiloto (T036, T039).
- Docs de endpoints/ops (T044) y test de schema de modelo dedicado (T016).