# Tasks: Silver Normalization

**Input**: Design documents from `specs/003-silver-normalization/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: La especificación exige verificaciones automatizadas y
conformance; el plan fija slices test-first. En cada historia se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido (contratos
silver-schema-v1 y dedupe-policy-v1, normalizadores puros, persistencia); la
geocodificación es P1 y queda dentro de US1 porque su trazabilidad la mapea a
US1.6/SC-006, pero puede diferirse al cierre sin bloquear el resto.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos versionados (silver-schema-v1 y
dedupe-policy-v1), el conjunto de referencia Silver y los límites de
arquitectura que usarán todas las historias.

- [X] T001 Definir el contrato silver-schema-v1 machine-checkable (precio sin
  conversión con `price_assumptions`, atributos con enums/rangos y códigos
  `silver.*`, ubicación y asignación de `geo_precision`, reglas de comparación
  de cambios) en `contracts/silver/v1/silver-schema.json` y
  `contracts/silver/v1/silver-schema.md`
- [X] T002 [P] Definir el contrato dedupe-policy-v1 machine-checkable
  (fingerprint de campos fuertes, reglas de degradación a propuesta,
  dimensiones de similitud con pesos, umbral, estados, esquema JSONB de
  evidencia) en `contracts/dedupe/v1/dedupe-policy.json` y
  `contracts/dedupe/v1/dedupe-policy.md`
- [X] T003 [P] Crear el conjunto de referencia Silver (12 registros: válidos,
  duplicados exactos same-source y cross-source, duplicados ambiguos, cambios
  de precio, campos faltantes, ubicaciones aproximadas y casos de cuarentena)
  en `tests/fixtures/silver/reference-batch.json`
- [X] T004 [P] Añadir fixtures de arquitectura para los límites de
  `application/silver` e `infrastructure/geocoding` (permite
  application→domain y adapters→application; prohíbe domain→infrastructure y
  silver→FastAPI/httpx en dominio) en `tests/architecture/`

**Checkpoint**: contratos publicados, conjunto de referencia disponible y
límites nuevos verificados desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Normalizadores puros (silver-schema, dedupe-policy), puerto
`Geocoder` y persistencia de las cuatro tablas. Nada de las historias comienza
sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T005 Escribir la conformance del silver-schema: precio sin conversión y
  con `price_assumptions`, rangos de atributos, asignación de `geo_precision`
  según granularidad, códigos `silver.*`, cero valores inventados en
  `tests/contract/test_silver_schema.py`
- [X] T006 Escribir la conformance del dedupe-policy: fingerprint exacto de
  campos fuertes, degradación a propuesta ante campo faltante, dimensiones de
  similitud con pesos renormalizados, umbral y evidencia en
  `tests/contract/test_dedupe_policy.py`
- [X] T007 Escribir los tests de migración `0004` (upgrade desde vacío y desde
  `0003`, head único, drift, downgrade) en `tests/migrations/test_0004_silver.py`
- [X] T008 Escribir los unit tests de repos y resolución canónica (guardas de
  unicidad `(snapshot_id, normalizer_version)` y `(source_id, external_id)`,
  lock optimista, `listing_a_id < listing_b_id`) en
  `tests/unit/application/silver/test_canonical_repos.py`

### Implementation for Foundational

- [X] T009 Definir los valores puros y errores (`NormalizedListing`,
  `CanonicalProperty`, `DedupeLink`, `ListingChange`, `GeoResult`,
  `NormalizationError`, errores tipados) en
  `src/umbral/application/silver/contracts.py`
- [X] T010 [P] Implementar el loader de silver-schema-v1 y `normalize_snapshot`
  puro (precio/costo total, atributos con rangos, ubicación + precisión,
  `normalization_errors`) en `src/umbral/application/silver/silver_schema.py`
- [X] T011 [P] Implementar el loader de dedupe-policy-v1 y `fingerprint`/
  `evaluate_pair` puros (campos fuertes, degradación, dimensiones, umbral,
  evidencia) en `src/umbral/application/silver/dedupe_policy.py`
- [X] T012 [P] Definir los puertos `Geocoder`, `SilverListingRepository`,
  `CanonicalPropertyRepository`, `DedupeLinkRepository` y `ChangeRepository` en
  `src/umbral/application/silver/ports.py`
- [X] T013 Implementar los modelos y ENUMs (`canonical_state`, `operation_type`,
  `property_type`, `currency_type`, `geo_precision`, `dedupe_method`,
  `dedupe_link_state`, `change_type`) con constraints/índices/geometría PostGIS
  y registrarlos en `src/umbral/infrastructure/db/models/silver.py` y
  `src/umbral/infrastructure/db/models/__init__.py`
- [X] T014 Crear la revisión `0004_silver_normalization` (down:
  `0003_bronze_ingestion`) con las cuatro tablas, los ENUMs y el chequeo de
  extensión PostGIS en `alembic/versions/0004_silver_normalization.py`
- [X] T015 [P] Implementar los repos SQLAlchemy (sin commit propio, version
  optimista, `WHERE id AND version`) en
  `src/umbral/infrastructure/db/repositories/silver.py`
- [X] T016 [P] Implementar los adapters in-memory para tests en `tests/fakes/silver.py`

**Checkpoint**: normalizadores puros, contratos y persistencia disponibles y
verificados; las historias pueden comenzar.

---

## Phase 3: User Story 1 — Normalizar listings persistentes y consultables (Priority: P1) MVP

**Goal**: cada snapshot capturado se convierte en un listing Silver consultable
con precio, atributos y ubicación confiables, listo para H2.3.

**Independent Test**: con el conjunto de referencia, normalizar produce listings
Silver con external id, URL, fuente, publicación, última observación y
referencia al snapshot de origen; 100% de precios con moneda/valor originales y
cero conversiones; atributos con rangos validados; precisión de ubicación
correcta; cero direcciones/coordenadas inventadas; los registros en cuarentena
no generan listings Silver.

### Tests for User Story 1

> Escribir T017–T020 primero y confirmar que fallan por la conducta ausente.

- [X] T017 [P] [US1] Escribir la integración de pipeline completa (import run →
  normalización → listings Silver con identidad/precio/atributos/precisión;
  cuarentenas sin silver; conteos del run) en
  `tests/integration/silver/test_normalization_pipeline.py`
- [X] T018 [P] [US1] Escribir los unit tests del handler `ingestion.normalize_batch`
  (slices por snapshots, inserción, resolución canónica within-source, conteos,
  fallo accionable) en `tests/unit/application/silver/test_normalize_handler.py`
- [X] T019 [P] [US1] Escribir la integración E2E de US1 (Postgres/PostGIS reales;
  reimport del mismo lote con misma identidad no duplica listings Silver) en
  `tests/integration/silver/test_normalization_pipeline_e2e.py`
- [X] T020 [P] [US1] Escribir los tests de geocoding (P1): `FakeGeocoder` y
  adapter comparten conformance, guard de precisión nunca mejora el input, rate
  limits y cache respetados, fallos degradan a `unknown` en
  `tests/unit/infrastructure/test_geocoding.py` y
  `tests/integration/silver/test_silver_geocoding.py`

### Implementation for User Story 1

- [X] T021 [US1] Implementar `SilverNormalizeHandler` (leer snapshots del run →
  normalizar por slice → insertar silver → resolver/crear canonical →
  finalizar con conteos) en `src/umbral/workers/silver.py`
- [X] T022 [US1] Registrar el job `ingestion.normalize_batch` en el registry y
  pasar los handlers al runtime en `src/umbral/workers/registry.py` y
  `src/umbral/workers/composition.py`
- [X] T023 [US1] Publicar el job encadenado al completar el import run con
  éxito (misma transacción, outbox, publish-before-commit) en
  `src/umbral/application/ingestion/service.py`
- [X] T024 [US1] Implementar `NormalizeRunService` (lecturas de listing y de
  cadena por `(source_id, external_id)`, resolución canónica within-source,
  `normalizer_version` derivada del loader) en
  `src/umbral/application/silver/service.py`
- [X] T025 [US1] Implementar el puerto `Geocoder`, `FakeGeocoder`, el adapter
  `NominatimGeocoder` (cache LRU, token-bucket, fuente registrada
  `osm.nominatim`, guard de precisión) y los settings `silver.geocoding_*`
  deshabilitados por default en `src/umbral/infrastructure/geocoding/`,
  `src/umbral/application/silver/ports.py` y
  `src/umbral/infrastructure/config/settings.py`

**Checkpoint**: US1 es un MVP demostrable — normalización Silver de punta a
punta con geocodificación opcional (P1).

---

## Phase 4: User Story 2 — Separar propiedad canónica y deduplicar con evidencia (Priority: P2)

**Goal**: distinguir la propiedad real de sus publicaciones y vincular
duplicados con evidencia, sin fusiones destructivas.

**Independent Test**: pares exactos same-source comparten una única property
canónica; pares cross-source con fingerprint completo quedan `confirmed` con
evidencia y misma canonical; pares ambiguos quedan `pending` con score y
evidencia y cero auto-merges; la transición pending→confirmed/rejected es
auditable y con lock optimista.

### Tests for User Story 2

> Escribir T026–T027 primero y confirmar que fallan por la conducta ausente.

- [X] T026 [P] [US2] Escribir los golden pairs (exactos same-source,
  exactos cross-source → confirmed + evidencia + misma canonical; ambiguos →
  pending; campo fuerte faltante → degradación a propuesta) en
  `tests/integration/silver/test_dedupe_golden.py`
- [X] T027 [P] [US2] Escribir los unit tests de transiciones de link
  (pending→confirmed/rejected, `listing_a_id < listing_b_id`, lock optimista,
  actor y timestamp auditados) en
  `tests/unit/application/silver/test_dedupe_service.py`

### Implementation for User Story 2

- [X] T028 [US2] Conectar la evaluación de pares y la creación de
  `dedupe_links` (deterministas `confirmed` y propuestas `pending`) en el
  handler en `src/umbral/workers/silver.py`
- [X] T029 [US2] Implementar `confirm_link`/`reject_link` (transición de estado
  con lock optimista, `decided_by`/`decided_at`) en
  `src/umbral/application/silver/service.py`
- [X] T030 [US2] Implementar la resolución canónica cross-source por
  fingerprint (vínculo confirmado agrupa en la misma canonical; propuestas no
  fusionan; resolución idempotente) en `src/umbral/application/silver/service.py`

**Checkpoint**: US1 y US2 funcionan — canonical properties y dedupe trazable y
no destructivo.

---

## Phase 5: User Story 3 — Registrar cambios y verificar lineage (Priority: P2)

**Goal**: ver qué cambió entre versiones y volver al dato crudo que produjo
cada entidad.

**Independent Test**: un cambio de precio emite `listing_changes` con
before/after/origen; cambios de texto/atributos idem; una re-publicación
idéntica emite cero cambios; un campo `status` sin definición en el contrato no
genera cambios; cada entidad Silver de referencia recorre su snapshot Bronze y
su versión de parser; reprocesar no duplica entidades ni genera cambios falsos.

### Tests for User Story 3

> Escribir T031–T033 primero y confirmar que fallan por la conducta ausente.

- [X] T031 [P] [US3] Escribir los tests de cambios entre versiones (precio,
  texto, atributos con before/after/origen; publicación idéntica → cero
  cambios; `status` sin contrato → cero cambios) en
  `tests/integration/silver/test_changes.py`
- [X] T032 [P] [US3] Escribir los tests de reproceso idempotente (mismo
  normalizer_version → cero duplicados y cero cambios falsos; nueva
  `normalizer_version` crea filas nuevas y conserva las previas) en
  `tests/integration/silver/test_reprocess_idempotency.py`
- [X] T033 [P] [US3] Escribir los tests de lineage Bronze-Silver (recorrido
  `silver_listings.snapshot_id` → `raw_listing_snapshots` → `import_runs` con
  parser y `normalizer_version`) en `tests/integration/silver/test_lineage.py`

### Implementation for User Story 3

- [X] T034 [US3] Emitir `listing_changes` entre versiones consecutivas de la
  cadena (comparación de campos normalizados; `before`/`after`/`origin`) en
  `src/umbral/application/silver/service.py`
- [X] T035 [US3] Implementar las lecturas de cambios y el lineage walk (por
  listing, por canonical, hasta snapshot y parser de origen) en
  `src/umbral/application/silver/service.py`
- [X] T036 [US3] Ajustar el handler para reproceso seguro (unicidad
  `(snapshot_id, normalizer_version)`, cero cambios falsos al reprocesar) en
  `src/umbral/workers/silver.py`

**Checkpoint**: US1–US3 funcionan — cambios auditables y lineage completo.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Harness propio, documentación operativa, telemetría y evidencia de
cierre.

- [X] T037 [P] Añadir `scripts/check-silver.ps1` (pytest de silver) y
  registrarlo en `scripts/check.ps1` siguiendo el patrón de `check-imports.ps1`
- [X] T038 [P] Documentar operación de normalización, dedupe y reproceso en
  `docs/runbooks/silver-normalization.md`
- [X] T039 [P] Registrar la evidencia de aceptación (comandos, resultados,
  métricas SC-001 a SC-008) en
  `docs/runbooks/evidence/silver-normalization-acceptance.md`
- [X] T040 Ejecutar `specs/003-silver-normalization/quickstart.md` de punta a
  punta y corregir cualquier desviación de contratos o guía
- [X] T041 [P] Verificar auditoría/telemetría metadata-only (sin valores
  normalizados, sin payloads, sin address text, sin secretos) y correlación
  import→normalize en `src/umbral/application/silver/` y
  `src/umbral/workers/silver.py`
- [X] T042 Ejecutar `.\scripts\check.ps1` desde un checkout limpio y cerrar la
  trazabilidad de cada FR/SC contra su evidencia automatizada

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P1)**: depende de Foundational; no depende de US2/US3.
- **US2 (P2)**: depende de Foundational y del handler de US1 (T021–T024);
  independientemente testeable después.
- **US3 (P2)**: depende de Foundational y del `NormalizeRunService` de US1
  (T024); no depende de US2.
- **Polish (final)**: depende de las historias deseadas.

### User Story Dependencies

- **US1**: `silver_schema`/`dedupe_policy` (T010/T011) + repos (T015/T016) +
  handler (T021) + chained publish (T023) + service (T024).
- **US2**: reusa el handler y `dedupe_policy`; agrega evaluación de pares,
  transiciones y canonical cross-source.
- **US3**: reusa el handler y el service; agrega emisión de cambios, lecturas de
  lineage y reproceso seguro.
- Trabajo secuencial recomendado: US1 → US2 → US3.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Valores/puertos antes de adapters; adapters antes de servicio; servicio antes
  de handler; handler antes de wiring del runtime.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003/T004 en Setup; T010/T011/T012, T015/T016 en Foundational;
  T017/T018/T019/T020 en US1; T026/T027 en US2; T031/T032/T033 en US3 — tocan
  archivos distintos sin dependencias.
- US2 y US3 pueden empezar en paralelo una vez que US1 deje handler y service
  estables (si hay capacidad).
- T037–T042 (Polish) son mayormente paralelizables salvo T040/T042 que cierran.

---

## Parallel Example: User Story 1

```bash
# Tests de US1 en paralelo:
Task: "Integración de pipeline en tests/integration/silver/test_normalization_pipeline.py"
Task: "Unit tests del handler en tests/unit/application/silver/test_normalize_handler.py"
Task: "E2E de US1 en tests/integration/silver/test_normalization_pipeline_e2e.py"
Task: "Tests de geocoding en tests/unit/infrastructure/test_geocoding.py"

# Valores y puertos en paralelo:
Task: "Valores puros en src/umbral/application/silver/contracts.py"
Task: "Puertos en src/umbral/application/silver/ports.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar Phase 3 (US1): normalización Silver de punta a punta (geocoding P1
   puede diferirse).
4. **STOP y VALIDAR** US1 con su Independent Test sobre Postgres/PostGIS real.
5. Demo/entrega si corresponde.

### Incremental Delivery

1. Setup + Foundational → contratos, normalizadores puros y persistencia listos.
2. US1 → import → Silver consultable → validar → demo (MVP).
3. US2 → canonical properties y dedupe con evidencia → validar.
4. US3 → cambios entre versiones y lineage → validar.
5. Polish → harness, runbook y evidencia de cierre.

### Parallel Team Strategy

1. Equipo completa Setup + Foundational juntos.
2. Tras Foundational: US1 primero (bloquea demos); US2/US3 pueden repartirse
   tras dejar handler y service de US1 estables.
3. Las historias integran sin romperse entre sí (tablas y jobs separados).

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
