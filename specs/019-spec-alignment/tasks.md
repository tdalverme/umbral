# Tasks: Cierre de alineacion con SPEC

**Input**: Design documents from `specs/019-spec-alignment/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md)

**Tests/checks**: Cada slice exige verificaciones automatizadas primero
(conformance de contratos, golden de extraccion, unit de reglas, integracion
del flujo). En cada historia se escriben primero los tests indicados y se
confirma que fallan por la conducta ausente antes de implementar.

**Organization**: Las tareas se agrupan por fase. Setup y Foundational
contienen solo trabajo compartido; US1/US2/US3 son slices demostrables
independientes sobre esa base.

## Format: `[ID] [P] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Schema de persistencia, contratos versionados y registry de
eventos listos para el feedback por concepto, sin romper v1.

- [X] T001 Crear migracion `alembic/versions/0019_feedback_strength_confidence.py`: columnas `strength` (ENUM `feedback_strength` `['low','medium','strong']`, nullable) y `confidence` (double precision, nullable) en `feedback_event_reasons`; registrar head en `tests/migrations/test_upgrade_and_drift.py`
- [X] T002 Crear `tests/migrations/test_0019_feedback_strength_confidence.py`: upgrade desde 0018, columnas presentes con default null, downgrade remove
- [X] T003 Crear `contracts/feedback/v1/feedback-concept-interpret-v1.json`: schema de salida estructurada de interpretacion `{concept_key, polarity (positive|negative), strength (low|medium|strong), confidence (0..1), evidence_text}`; validable contra el catalogo activo (solo conceptos computables); forbidden keys sin PII
- [X] T004 Actualizar `contracts/events/v1/events-registry.json`: `feedback.recorded.v1` admite el payload extendido (p.ej. `concept_reason_count`) sin romper la validacion estricta existente (version o clave nueva segun convencion; ver `application/events/registry.py`)
- [X] T005 Actualizar el tool contract del agente (`contracts/agent/tools/tool-contract-v2.json` o nueva version v3 segun convencion de versionado): `record_feedback.input_schema` agrega `concept_feedback` (array de `{concept_key, polarity, strength, confidence}`) con output_limits/redaction coherentes
- [X] T006 Actualizar `src/umbral/infrastructure/db/models/feedback.py` + `db/repositories/feedback.py` para persistir `strength`/`confidence` en `FeedbackEventReason`

**Checkpoint**: `pytest tests/migrations tests/contract/test_events_registry.py` pasan; la migracion 0019 aplica limpio; el registry valida con el payload nuevo.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Conformance y pruebas que guian la implementacion de US1.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

- [X] T007 [P] Escribir conformance de `feedback-concept-interpret-v1.json` en `tests/contract/test_feedback_concept_interpret.py`: schema valido, conceptos solo del catalogo activo y computables, forbidden keys, strength/confidence en rangos
- [X] T008 [P] Escribir test del registry extendido en `tests/contract/test_events_registry.py` (o archivo nuevo): `feedback.recorded.v1` acepta `concept_reason_count`; 0 keys PII
- [X] T009 [P] Escribir test del tool contract actualizado en `tests/contract/test_agent_tools_contract.py` (o bundle existente): `record_feedback` acepta `concept_feedback` y rechaza conceptos desconocidos/campos extra

**Checkpoint**: los tres conformance fallan por la conducta ausente (contratos
aun sin actualizar) — red estable hasta Phase 1 completa.

---

## Phase 3: User Story 1 - Feedback libre que alimenta el aprendizaje por concepto (Priority: P1) MVP

**Goal**: "me gusta pero la cocina es chica e integrada" produce reasons por
concepto con strength/confidence y, al alcanzar el umbral del policy, una
`LearningProposal` pendiente confirmable; jamas auto-apply.

**Independent Test**: dos `like` razonados con `tipo_cocina` negative dentro de
la ventana producen una proposal pendiente con `evidence_event_ids`; un concepto
fuera de catalogo se preserva como texto.

### Tests for User Story 1

> Escribir T010-T013 primero y confirmar que fallan por la conducta ausente.

- [X] T010 [P] [US1] Escribir unit en `tests/unit/application/feedback/test_concept_signals.py`: reasons con concepto alimentan `evaluate_signals` (conteo por polaridad, ventana, `min_signals`), strength/confidence no alteran el conteo (FR-004), 0 auto-apply
- [X] T011 [P] [US1] Escribir unit de service en `tests/unit/application/feedback/test_concept_signals.py` y `tests/unit/application/feedback/test_feedback_service.py`: `record_feedback` acepta `concept_feedback`, persiste reasons extendidos, respeta idempotency_key y supersesion append-only
- [X] T012 [P] [US1] Escribir integracion en `tests/integration/feedback/test_concept_feedback_e2e.py`: feedback con concepto -> proposal pendiente -> confirm -> `PreferenceFact` + radar versionado + nuevo run (sobre Postgres real)
- [X] T013 [P] [US1] Escribir tests de agente en el bundle de tools existente: payload `concept_feedback` validado, concepto fuera de catalogo -> preservado textual con sugerencia, redaction/0 PII

### Implementation for User Story 1

- [X] T014 [US1] Implementar en `src/umbral/application/feedback/contracts.py` y `service.py`: `record_feedback` consume `concept_feedback[]` (schema versionado), persiste `FeedbackEventReason` con strength/confidence y traza al `free_feedback`
- [X] T015 [US1] Verificar `signals.py`: los reasons por concepto ya calzan en `Signal(concept_key, polarity)`; ajustar solo si hace falta la lectura de reasons activos (sin tocar policy ni thresholds)
- [X] T016 [US1] Implementar en `src/umbral/agent/tools/` + `tools/tools.py`: interpretacion estructurada del texto libre hacia `feedback-concept-interpret-v1` (patron `preference_interpreter`) y delegacion del payload al service; 0 conceptos inventados
- [X] T017 [US1] Verificar `contracts/agent/tools/` loader y la abuse suite (tool contract v3 o extension) sin regresiones: `pytest tests/contract/test_agent_tools_contract.py tests/unit/agent`

**Checkpoint**: `test_concept_feedback_e2e.py` verde; `scripts/check-agent-tools.ps1` y `check-feedback.ps1` sin regresiones.

---

## Phase 4: User Story 2 - Conceptos economicos de regla (Priority: P2)

**Goal**: `precio_m2` y `variacion_precio` observables por regla con goldens y
vocabulario, sin infraestructura nueva.

**Independent Test**: listing con `price`+`surface_m2` observa `precio_m2`;
listing con `listing_changes` de precio observa `variacion_precio`; sin datos ->
`unknown`.

### Tests for User Story 2

> Escribir T018-T020 primero y confirmar que fallan por la conducta ausente.

- [X] T018 [P] [US2] Escribir golden de extraccion en `tests/contract/test_extraction_goldens_v2.py` (o archivo nuevo): casos `precio_m2` (precio/superficie, unknown sin superficie, moneda del listado) y `variacion_precio` (baja/igual/subida, unknown sin cambios)
- [X] T019 [P] [US2] Escribir unit en `tests/unit/application/criteria/test_rules_economic.py`: `run_precio_m2` cociente documentado con evidencia de campos; `run_variacion_precio` convencion de signo y evidencia del `listing_changes`
- [X] T020 [P] [US2] Actualizar tests de set exacto que cambian con el catalogo (patron de 018/T014): registry, extraction, invalidation

### Implementation for User Story 2

- [X] T021 [US2] Extender `contracts/criteria/v2/concepts-seed-v2.json` (o v3 si 018 se libero) con `precio_m2` y `variacion_precio` (matcher `numeric_range`, computables, unknown declarado) + `contracts/criteria/v2/extraction-v2.json` (source rule)
- [X] T022 [US2] Implementar reglas en `src/umbral/application/criteria/rules.py`: `run_precio_m2` (misma moneda, sin conversion no versionada) y `run_variacion_precio` (desde `listing_changes` tipo `price`), registradas en `RULE_RUNNERS`
- [X] T023 [US2] Agregar entradas de vocabulario en `contracts/criteria/v1/preferences-vocabulary-v1.json` (o version nueva) para que el copiloto proponga los conceptos; respetar invariante vocab->concept
- [X] T024 [US2] Verificar ciclo: seed-local registra el catalogo, `process_extraction(full)` produce observaciones activas para los dos conceptos con `source=rule`

**Checkpoint**: goldens y unit verdes; `scripts/check-criteria.ps1` y `check-urban.ps1` (si aplica) sin regresiones.

---

## Phase 5: User Story 3 - Flujo de validacion golden-path (Priority: P1)

**Goal**: un test de integracion unico demuestra los dos flujos de la SPEC
sobre Postgres real con adapters deterministicos.

**Independent Test**: flujo A completo hasta explicacion del top 1; flujo B
feedback por concepto -> proposal -> confirm -> nuevo run que refleja el hecho.

### Tests for User Story 3

> Escribir T025 primero y confirmar que falla por la conducta ausente.

- [X] T025 [US3] Escribir `tests/integration/flows/test_spec_validation_flows.py`: seed sintetico (import -> silver -> extraccion regla+urban con fakes) -> run -> explicacion (citando evidencia); luego feedback `concept_feedback` -> proposal -> confirm -> radar versionado + nuevo run con contribucion nueva; assert de idempotencia del feedback
- [X] T026 [US3] Registrar el bundle en el harness: `scripts/check-019.ps1` (o inclusion en bundle existente de feedback/integration) e invocarlo desde `scripts/check.ps1`

### Implementation for User Story 3

- [X] T027 [US3] Ajustar fixtures/fakes si hace falta (geocoder determinista, extractor de reglas, snapshot urbano minimo) para que el flujo corra sin servicios externos
- [X] T028 [US3] Verificar determinismo: dos corridas del flujo producen el mismo orden y las mismas explicaciones (patron de `test_run_v1.py`)

**Checkpoint**: `test_spec_validation_flows.py` verde en el harness local y en CI; 0 regresiones en `scripts/check.ps1`.

---

## Phase 6: Cierre (Docs & Traza)

**Purpose**: Cerrar el loop con documentacion conforme a la convencion del repo.

- [X] T029 Actualizar `CONTEXT.md` si hace falta (conceptos nuevos: `precio_m2`, `variacion_precio`; fuerza como evidencia de feedback)
- [X] T030 Escribir `docs/runbooks/evidence/019-spec-alignment-acceptance.md` documentando: ADRs referenciados, flujos demostrados, checks verdes y backlog explicitado (imagenes, days_on_market, comparables, session overrides, price_drop, capa derivada) — sin codigo futuro
- [ ] T031 Verificacion final: `./scripts/check.ps1` completo (ruff, mypy strict, import-linter, pytest, migrations) sin regresiones; `specify.exe check` si el folder 019 es la feature activa — bloqueada en este entorno por acceso denegado al daemon Docker y `specify.exe` no instalado
