# Tasks: Calidad del matching

**Input**: Design documents from `specs/008-matching-quality/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice starts
with the failing contract/unit test named here"). En cada fase se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido
(contratos `matching/v1`: golden dataset + schema, releases, forbidden
features; flag aditivo `compute_policy.computable` en el concepts seed; dominio
puro: `contracts.py`, `golden.py`, `releases.py`; settings). US1 entrega el
dataset golden con conformance; US2 las regresiones de scoring con gate
estricto; US3 la fidelidad de explicaciones; US4 la revisión de fairness (P1);
Polish el report y el harness.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos machine-checkable de matching (golden
dataset + schema, releases, forbidden features), el flag aditivo
`compute_policy.computable` en el concepts seed y los límites de arquitectura
que usarán todas las historias.

- [X] T001 Definir el dataset golden machine-checkable (contract_version,
  registry_version `golden-dataset-v1`, reviewed_by/reviewed_at,
  baseline_score_policy_version, casos con id/tags/profile_criteria/listings/
  expected_ranking/expected_hard_filter/notes) en
  `contracts/matching/v1/golden-dataset-v1.json`
- [X] T002 [P] Definir el JSON Schema del dataset golden (estructura, tipos,
  required, uniqueness de ids, referencias entre expected_ranking y listings)
  en `contracts/matching/v1/golden-dataset.schema.json`
- [X] T003 [P] Definir el registro de releases machine-checkable
  (contract_version, registry_version `matching-releases-v1`, releases con
  id/artifact/artifact_version/owner/justification/affected_case_ids/date) en
  `contracts/matching/v1/releases-v1.json`
- [X] T004 [P] Definir el registro de forbidden features machine-checkable
  (contract_version, registry_version `forbidden-features-v1`,
  forbidden_concepts con concept_key/justification, forbidden_proxies,
  normative_phrases) en `contracts/matching/v1/forbidden-features-v1.json`
- [X] T005 [P] Añadir el flag aditivo `compute_policy.computable` (default
  `true` cuando falta) a los conceptos del seed y marcar los conceptos
  prohibidos como `computable: false` en
  `contracts/criteria/v1/concepts-seed-v1.json`
- [X] T006 [P] Añadir fixtures de arquitectura para los límites de
  `application/matching` (puro, test-only: permite application→domain y
  adapters→application; prohíbe domain→infrastructure, matching→FastAPI/web/
  LLM/direct-DB, y cualquier import desde `api/` o workers) en
  `tests/architecture/test_matching_boundaries.py`

**Checkpoint**: contratos publicados, flag de conceptos añadido y límites
nuevos verificados desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Dominio puro de matching (valores/errores, loader/validador del
golden dataset, loader/validador de releases) y settings. Nada de las historias
comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T007 Escribir la conformance del golden dataset: parse/validación
  (estructura, schema, uniqueness de ids, expected_ranking ⊆ listings, tags
  conocidos, cobertura por categoría requerida, criteria válidos contra
  `matcher-types-v1.json`) y seed `golden-dataset-v1` cargable en
  `tests/contract/test_matching_golden.py`
- [X] T008 [P] Escribir la conformance de releases: parse/validación
  (ids únicos, artifact_version única, affected_case_ids existentes en el
  dataset) y seed `releases-v1` cargable en `tests/contract/test_matching_regression.py`
- [X] T009 [P] Escribir los unit tests de los loaders puros
  (`load_golden_dataset`, `load_releases`, errores tipados sobre documentos
  inválidos) en `tests/unit/application/matching/test_loaders.py`

### Implementation for Foundational

- [X] T010 Definir los valores puros y errores (`GoldenDataset`, `GoldenCase`,
  `CaseTags`, `Release`, `ReleasesRegistry`, `MatchingError` y subclases
  tipadas) en `src/umbral/application/matching/contracts.py`
- [X] T011 [P] Implementar el loader/validador puro del golden dataset
  (`load_golden_dataset`, `validate_golden_dataset`) contra el contrato y el
  schema en `src/umbral/application/matching/golden.py`
- [X] T012 [P] Implementar el loader/validador puro de releases
  (`load_releases`, `validate_releases`, `declared_affected`) contra el
  contrato en `src/umbral/application/matching/releases.py`
- [X] T013 Añadir los settings `matching.*` (`golden_dataset_version`
  `golden-dataset-v1`, `regression_gate_enabled` true) validados al iniciar en
  `src/umbral/infrastructure/config/settings.py` con su test

**Checkpoint**: dominio puro, loaders y settings disponibles y verificados;
las historias pueden comenzar.

---

## Phase 3: User Story 1 — Proteger el matching con un dataset golden (Priority: P0) MVP

**Goal**: el dataset golden versionado con orden esperado revisado por producto
queda disponible, trazable y validado por conformance; es la referencia de las
regresiones y la fidelidad.

**Independent Test**: el dataset construido cubre las categorías requeridas
(hard filter violations, unknowns, preferencias subjetivas, precio/expensas,
legacy), cada caso traza a sus listings/criterios y tiene orden esperado
documentado; 0 versiones se mutan (SC-001).

### Tests for User Story 1

> Escribir T014 primero y confirmar que falla por la conducta ausente.

- [X] T014 [P] [US1] Añadir los casos golden curados del dataset (al menos un
  caso por tag: `hard_filter_violation`, `unknown`, `subjective_preference`,
  `price_boundary`, `legacy_no_breakdown`) con listings/criterios y orden
  esperado en `contracts/matching/v1/golden-dataset-v1.json`

### Implementation for User Story 1

- [X] T015 [US1] Completar la conformance de cobertura y trazabilidad del
  dataset (cada tag requerido presente, cada expected_ranking id existe en
  listings, criteria válidos) en `tests/contract/test_matching_golden.py`

**Checkpoint**: dataset golden validado por conformance; US1 cerrada.

---

## Phase 4: User Story 2 — Automatizar regresiones de scoring (Priority: P0)

**Goal**: el runner compara dos revisiones de policy sobre el dataset golden;
cualquier cambio de orden relativo o de hard filters bloquea salvo que una
release declare exactamente los casos afectados; las diferencias de score sin
cambio de orden son informativas.

**Independent Test**: correr el mismo dataset contra dos versiones reporta
veredictos por caso; un cambio no explicado bloquea con el diff; una release
declarada con cases coincidentes pasa; ids divergentes bloquean; las
regresiones de hard filters son siempre bloqueantes (SC-002, SC-003).

### Tests for User Story 2

> Escribir T016–T017 primero y confirmar que fallan por la conducta ausente.

- [X] T016 [P] [US2] Escribir los unit tests de `run_regression` (gate estricto
  de orden/hard filters, score deltas informativos, verificación de cobertura
  de releases contra el diff real) en
  `tests/unit/application/matching/test_regression.py`
- [X] T017 [P] [US2] Escribir la conformance de regresión end-to-end sobre el
  dataset golden (baseline vs candidata con y sin release, cambio inducido no
  declarado bloquea, mismatch de cases ids bloquea, hard filter change siempre
  bloquea) en `tests/contract/test_matching_regression.py`

### Implementation for User Story 2

- [X] T018 [US2] Implementar `run_regression` puro (invoca el engine de H3.2
  sobre los casos, compara orden relativo/hard filters/score, aplica el gate
  estricto de la clarificación 2026-08-09 y verifica la cobertura de releases)
  en `src/umbral/application/matching/regression.py`

**Checkpoint**: regresiones verificadas por unit + conformance; US2 cerrada.

---

## Phase 5: User Story 3 — Evaluar la fidelidad de las explicaciones (Priority: P0)

**Goal**: el evaluador clasifica cada claim de una explicación como
`supported`/`unsupported`/`contradiction` contra el breakdown persistido de
H3.2, verifica la declaración de incertidumbre y aplica el umbral estricto
(100% supported, 0 unsupported, 0 contradictions); los legacy se reportan
`no_breakdown` sin fabricar razones.

**Independent Test**: claims soportados, no soportados y contradictorios se
distinguen; los desconocidos/confianza baja se declaran; un único claim no
soportado o contradictorio falla el reporte; los legacy nunca fallan con
razones fabricadas (SC-004).

### Tests for User Story 3

> Escribir T019–T020 primero y confirmar que fallan por la conducta ausente.

- [X] T019 [P] [US3] Escribir los unit tests de `evaluate_fidelity`
  (clasificación supported/unsupported/contradiction, declaración de
  incertidumbre, threshold estricto, legacy `no_breakdown`) en
  `tests/unit/application/matching/test_fidelity.py`
- [X] T020 [P] [US3] Escribir la conformance de fidelidad sobre fixtures del
  breakdown de H3.2 (casos con claims soportados/contradictorios/unknowns y
  legacy) en `tests/contract/test_matching_fidelity.py`

### Implementation for User Story 3

- [X] T021 [US3] Implementar `evaluate_fidelity` puro (clasifica claims contra
  el breakdown persistido y sus evidence refs, verifica incertidumbre, aplica
  el threshold estricto de la clarificación 2026-08-09, reporta legacy como
  `no_breakdown`) en `src/umbral/application/matching/fidelity.py`

**Checkpoint**: fidelidad verificada por unit + conformance; US3 cerrada.

---

## Phase 6: User Story 4 — Revisar fairness y lenguaje geografico (Priority: P1)

**Goal**: el registro de forbidden features queda publicado y validado; los
conceptos prohibidos son `computable: false` en el seed y el compilador los
rechaza; el escáner de frases normativas pasa sobre los templates; el documento
de fairness queda referenciado.

**Independent Test**: `forbidden-features-v1.json` valida; cada concepto
prohibido es `computable: false` y el compilador rechaza compilaciones que lo
referencien; 0 frases normativas en templates; el documento de fairness existe
(SC-005).

### Tests for User Story 4

> Escribir T022–T023 primero y confirmar que fallan por la conducta ausente.

- [X] T022 [P] [US4] Escribir la conformance de fairness (validación del
  registro, linkage de conceptos prohibidos a `computable: false` en el seed,
  rechazo del compilador, escáner de frases normativas sobre templates) en
  `tests/contract/test_matching_fairness.py`
- [X] T023 [P] [US4] Escribir los unit tests del compilador de criterios con
  conceptos no computables (rechazo tipado) en
  `tests/unit/application/criteria/test_compile_forbidden_concepts.py`

### Implementation for User Story 4

- [X] T024 [P] [US4] Implementar el loader/validador de forbidden features y el
  escáner de frases normativas en `src/umbral/application/matching/fairness.py`
- [X] T025 [P] [US4] Exponer el flag `compute_policy.computable` en el parseo
  del concept registry (default `true`) y rechazar en el compilador las
  compilaciones que referencien conceptos no computables en
  `src/umbral/application/criteria/registry.py`,
  `src/umbral/application/criteria/contracts.py` y
  `src/umbral/application/criteria/compile.py`
- [X] T026 [P] [US4] Escribir el documento versionado de revisión de fairness
  (hallazgos, features/proxies prohibidos con justificación, frases
  normativas evitadas, decisiones de copy) en
  `docs/product/fairness-review-v1.md`

**Checkpoint**: fairness y lenguaje geografico verificados; US4 cerrada.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: report auditable sin PII, harness dedicado, evidencia de cierre y
gate completo. Nada de esto cambia el comportamiento de producto.

- [X] T027 Escribir el test de que el report del harness no contiene PII y 0
  eventos de producto/endpoints/migraciones se agregan por el incremento en
  `tests/contract/test_matching_harness.py`
- [X] T028 [P] Implementar el builder de report auditables (ids de caso,
  veredictos, conteos, release ids; 0 texto de listings/perfiles) en
  `src/umbral/application/matching/report.py`
- [X] T029 [P] Crear `scripts/check-matching.ps1` (conformance + unit de
  matching sobre fixtures en memoria) y registrarlo con el guard
  `matchingSurface` en `scripts/check.ps1`
- [X] T030 [P] Escribir la evidencia de cierre del incremento en
  `docs/runbooks/evidence/matching-quality-acceptance.md` (resultado de cada SC
  del spec y recorrido de los escenarios de
  `specs/008-matching-quality/quickstart.md`)
- [X] T031 [P] Actualizar el quickstart del feature con el resultado real de
  cada escenario y los settings `matching.*` en
  `specs/008-matching-quality/quickstart.md`
- [X] T032 Verificar el gate completo desde checkout limpio:
  `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`,
  `uv run pytest`, `uv run alembic current --check-heads`, `uv run alembic check`
  y `.\scripts\check.ps1`; documentar el resultado en la evidencia de cierre

---

## Dependencies

- **Setup (Phase 1)**: sin dependencias; publica contratos y fixtures.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P0)**: depende de Foundational (loaders/golden, T011); independiente
  de US2–US4.
- **US2 (P0)**: depende de Foundational (`releases.py` T012, `golden.py` T011)
  y de US1 (casos del dataset, T014); independiente de US3/US4.
- **US3 (P0)**: depende de Foundational (valores/errores, T010) y de US1
  (dataset como referencia); independiente de US2/US4.
- **US4 (P1)**: depende de Foundational (valores/errores, T010) y de Setup
  (forbidden features + flag computable, T004/T005); independiente de US1–US3.
- **Polish (final)**: depende de las historias deseadas (T027/T028/T029/T030
  son paralelizables con las historias tardías).

### User Story Dependencies

- **US1**: `golden.py` (T011) + casos curados (T014) + conformance (T015).
- **US2**: reusa `golden.py` + `releases.py`; agrega `run_regression` (T018).
- **US3**: reusa `contracts.py`; agrega `evaluate_fidelity` (T021).
- **US4**: reusa `contracts.py`; agrega `fairness.py` (T024) + flag en registry/
  compiler (T025) + documento (T026).
- Trabajo secuencial recomendado: US1 → US2 → US3 → (US4 ∥ Polish) → Polish.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Dominio puro antes del runner/evaluador; conformance al final de la historia.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003/T004/T005/T006 en Setup; T008/T009, T011/T012 en Foundational;
  T014 en US1; T016/T017 en US2; T019/T020 en US3; T022/T023, T024/T025/T026 en
  US4; T027/T028/T029/T030/T031 en Polish — tocan archivos distintos sin
  dependencias.
- Tras Foundational, US1 y US4 pueden empezar en paralelo; US2 sigue a US1;
  US3 sigue a US1; Polish puede preparar report y harness en paralelo con US4.

---

## Parallel Example: User Story 2

```bash
# Tests de US2 en paralelo:
Task: "Unit tests de run_regression en tests/unit/application/matching/test_regression.py"
Task: "Conformance de regresión end-to-end en tests/contract/test_matching_regression.py"

# Implementación (única por fase):
Task: "run_regression en src/umbral/application/matching/regression.py"
```

---

## Implementation Strategy

### MVP First (Camino crítico P0 del backlog)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar US1 a US3 en orden (dataset golden → regresiones → fidelidad):
   cubren UM-H3-032 a UM-H3-034.
4. **STOP y VALIDAR** cada historia con su Independent Test sobre los fixtures
   del dataset golden antes de continuar.
5. Primer recorrido interno del hito: US1–US3 con harness.
6. Demo/entrega si corresponde; US4 (P1) y Polish después.

### Incremental Delivery

1. Setup + Foundational → contratos, flag computable y dominio puro listos.
2. US1 → dataset golden validado → demo (MVP).
3. US2 → regresiones con gate estricto → validar.
4. US3 → fidelidad de explicaciones → validar (camino crítico
   UM-H3-032..034).
5. US4 → fairness y lenguaje geografico → validar (P1).
6. Polish → report, harness, evidencia de cierre.

### Parallel Team Strategy

1. Equipo completo Setup + Foundational juntos.
2. Tras Foundational: US1 y US4 en paralelo (US4 es P1 y no depende de los
   casos del dataset).
3. Tras US1: US2 y US3 en paralelo (runner y evaluador tocan archivos
   distintos).
4. Polish prepara report y harness en paralelo con US3/US4.
5. Las historias integran sin romperse entre sí (contratos, dominio y tests
   separados; el contrato del dataset crece aditivamente).

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
- No crear un job, endpoint, evento de producto, migración ni superficie web
  nueva: el incremento es verificación interna (R-06, FR-011).
- El gate de regresión es estricto (clarificación 2026-08-09): cualquier cambio
  de orden relativo o de hard filters bloquea; los score deltas sin cambio de
  orden son informativos.
- Un cambio está "explicado" solo si la release declara exactamente los casos
  afectados detectados (clarificación 2026-08-09, FR-005).
- La fidelidad usa threshold estricto (clarificación 2026-08-09): 100% de
  claims soportados, 0 unsupported, 0 contradictions.
- Los legacy (baseline sin desglose) se reportan `no_breakdown` y nunca fallan
  con razones fabricadas (R-04, FR-007 edge case).
- El flag `compute_policy.computable` es aditivo con default `true` cuando
  falta; los fixtures de conformance existentes de criteria deben seguir
  pasando (cambio de contrato, no de migración).
- El módulo `application/matching` es puro y test-only: nunca se importa desde
  `api/` ni workers (R-06, FR-011).
- El report del harness no contiene PII: solo ids de caso, veredictos, conteos
  y release ids (FR-011).
