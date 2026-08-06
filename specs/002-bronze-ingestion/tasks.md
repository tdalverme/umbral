# Tasks: Bronze Ingestion

**Input**: Design documents from `specs/002-bronze-ingestion/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: La especificaciÃ³n exige verificaciones automatizadas y
conformance; el plan fija slices test-first. En cada historia se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sÃ³lo trabajo compartido (contrato,
validator, puerto ImportSource, persistencia); las integraciones transversales
quedan explÃ­citas en las fases US y en el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar el contrato controlado v1, los lotes de referencia y los
lÃ­mites de arquitectura que usarÃ¡n todas las historias.

- [X] T001 Definir el contrato controlado v1 machine-checkable con reglas de
  archivo (JSON/CSV, UTF-8, 10 MiB, versiÃ³n soportada `"1"`) y reglas por
  registro (campos requeridos/opcionales, tipos, enums, rangos, cÃ³digos de
  cuarentena) en `contracts/import/v1/import-contract.json` y
  `contracts/import/v1/import-contract.md`
- [X] T002 [P] Crear el lote de referencia (12 registros: 9 vÃ¡lidos, 2
  invÃ¡lidos, 1 duplicado intra-lote, 3 con opcional faltante) en versiÃ³n JSON y
  CSV en `tests/fixtures/imports/reference-batch.json` y
  `tests/fixtures/imports/reference-batch.csv`
- [X] T003 [P] AÃ±adir fixtures de arquitectura para los lÃ­mites de
  `application/ingestion` e `infrastructure/sources` (permite
  applicationâ†’domain y adaptersâ†’application; prohÃ­be domainâ†’infrastructure)
  en `tests/architecture/`

**Checkpoint**: el contrato estÃ¡ publicado, los lotes de referencia existen y
los lÃ­mites nuevos se verifican desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Validator puro del contrato, puerto `ImportSource` con adapters y
persistencia de las tres tablas. Nada de las historias comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T004 Escribir la conformance del contrato: lotes invÃ¡lidos por formato,
  encoding, tamaÃ±o o versiÃ³n con diagnÃ³stico accionable, y violaciones por
  registro con cÃ³digo/rule/detail en `tests/contract/test_import_contract.py`
- [X] T008 Escribir la conformance compartida de adapters: `FileImportSource` y
  `FakeImportSource` producen los mismos records y reporte en
  `tests/unit/infrastructure/test_import_source.py`
- [X] T011 Escribir los tests de migraciÃ³n `0003` (upgrade desde vacÃ­o y desde
  `0002`, head Ãºnico, drift) en `tests/migrations/test_0003_ingestion.py`
- [X] T016 Escribir los unit tests del run service (transiciones
  pendingâ†’runningâ†’succeeded/failed, replay terminal, conteos derivados) en
  `tests/unit/application/ingestion/test_import_run_service.py`
- [X] T018 Escribir la integraciÃ³n de persistencia (transiciones y conflicto
  optimista sobre Postgres real) en `tests/integration/ingestion/test_import_runs.py`

### Implementation for Foundational

- [X] T005 Implementar el loader del contrato y `validate_record` puro (tipos,
  enums, rangos, required/optional; cÃ³digos estables) en
  `src/umbral/application/ingestion/import_contract.py`
- [X] T006 [P] Definir los valores puros y errores (`ImportBatch`, `RawRecord`,
  `RawListingSnapshot`, `QuarantineRecord`, `ImportRunSnapshot`,
  `ValidationResult`, errores tipados) en `src/umbral/application/ingestion/contracts.py`
- [X] T007 [P] Definir los puertos `ImportSource`, `ImportRunRepository`,
  `RawSnapshotRepository` y `QuarantineRepository` en
  `src/umbral/application/ingestion/ports.py`
- [X] T009 Implementar `FileImportSource` (JSON envelope/CSV, UTF-8, lÃ­mite de
  tamaÃ±o, reporte de ingesta sin conocer Silver) en
  `src/umbral/infrastructure/sources/file_source.py`
- [X] T010 [P] Implementar `FakeImportSource` con el mismo comportamiento
  observable en `src/umbral/infrastructure/sources/fake_source.py`
- [X] T012 Implementar los modelos y ENUMs (`import_format`, `import_run_state`)
  con constraints/Ã­ndices/auditorÃ­a y registrarlos en
  `src/umbral/infrastructure/db/models/imports.py` y
  `src/umbral/infrastructure/db/models/__init__.py`
- [X] T013 Crear la revisiÃ³n `0003_bronze_ingestion` (down:
  `0002_private_beta_identity`) con las tres tablas en
  `alembic/versions/0003_bronze_ingestion.py`
- [X] T014 [P] Implementar los repos SQLAlchemy (sin commit propio, version
  optimista) en `src/umbral/infrastructure/db/repositories/imports.py`
- [X] T015 [P] Implementar los adapters in-memory para tests en `tests/fakes/imports.py`
- [X] T017 Implementar `ImportRunService.submit/get` con transiciones de estado,
  replay terminal y conteos derivados de filas comprometidas en
  `src/umbral/application/ingestion/service.py`

**Checkpoint**: validator, adapters y persistencia disponibles y verificados;
las historias pueden comenzar.

---

## Phase 3: User Story 1 â€” Importar un lote controlado de punta a punta (Priority: P1) MVP

**Goal**: Un operador sube un lote controlado, ve el run y obtiene snapshots
crudos inmutables y cuarentena, sin errores silenciosos.

**Independent Test**: con el lote de referencia, subir por la entrada
operativa produce un run `succeeded` con `total=12 accepted=9 quarantined=2
duplicates=1 missing_fields=3`, 9 snapshots con hash verificable y 2
cuarentenas consultables; una persona sin rol operador es rechazada y el
intento queda auditado.

### Tests for User Story 1

> Escribir T019â€“T020 y T024 primero y confirmar que fallan por la conducta ausente.

- [X] T019 [P] [US1] Escribir la integraciÃ³n de captura completa (submit â†’
  `succeeded` â†’ snapshots + cuarentena + raw object con SHA-256 verificado) en
  `tests/integration/ingestion/test_capture_pipeline.py`
- [X] T020 [P] [US1] Escribir los unit tests del handler `ingestion.import_batch`
  (validaciÃ³n, objetos, inserciones, conteos, fallo accionable) en
  `tests/unit/application/ingestion/test_import_handler.py`
- [X] T024 [P] [US1] Escribir los tests de API submit/read y autorizaciÃ³n
  (operator/administrator OK; user/anonymous 401/403 auditado; URL en lugar de
  archivo rechazada; batch invÃ¡lido 400 con cÃ³digo accionable) en
  `tests/unit/api/test_imports.py` y
  `tests/integration/identity/test_import_authorization.py`

### Implementation for User Story 1

- [X] T021 [US1] Implementar `IngestionImportHandler` (validar â†’ escribir raw
  object â†’ insertar snapshots/cuarentena â†’ derivar conteos â†’ finalizar run) en
  `src/umbral/workers/imports.py`
- [X] T022 [US1] Registrar el job `ingestion.import_batch` en el registry y pasar
  los handlers al runtime en `src/umbral/workers/registry.py` y
  `src/umbral/workers/composition.py`
- [X] T023 [US1] Integrar el seam de objetos (`purpose=ingestion.raw_batch`,
  integridad tamaÃ±o/SHA-256, disponibles sÃ³lo versiÃ³n exacta) en
  `src/umbral/application/ingestion/service.py` y `src/umbral/workers/imports.py`
- [X] T025 [US1] AÃ±adir las acciones `ops.ingestion.batch.submit` y
  `ops.ingestion.run.read` (operator/administrator, deny-by-default) en
  `src/umbral/domain/identity/policy.py`
- [X] T026 [US1] Implementar `POST /api/v1/imports/batches` y
  `GET /api/v1/imports/runs/{run_id}` (multipart file-only, sin URLs,
  `batch_key` derivada como SHA-256 por defecto, errores Problem) en
  `src/umbral/api/routers/imports.py`
- [X] T027 [US1] Componer el router y las dependencias del API en
  `src/umbral/api/dependencies.py` y `src/umbral/api/main.py`
- [X] T028 [US1] Exportar OpenAPI y regenerar el cliente web sin drift en
  `scripts/export-openapi.ps1`, `contracts/openapi/v1/openapi.json` y
  `apps/web/src/lib/api/generated/`
- [X] T029 [US1] Escribir y pasar la integraciÃ³n E2E de US1 (Postgres + object
  storage reales; reimporte con misma clave devuelve el mismo run) en
  `tests/integration/ingestion/test_import_pipeline_e2e.py`

**Checkpoint**: US1 es un MVP demostrable â€” importaciÃ³n de punta a punta con
snapshots, cuarentena y permisos.

---

## Phase 4: User Story 2 â€” Repetir una importaciÃ³n sin duplicar efectos (Priority: P2)

**Goal**: Reintentar el mismo lote con la misma clave idempotente sin duplicar
snapshots ni efectos.

**Independent Test**: reimportar el lote de referencia con la misma `batch_key`
devuelve el mismo run con cero snapshots nuevos; mismo contenido con otra clave
crea un run nuevo pero cero snapshots duplicados; un retry tras una
interrupciÃ³n no deja filas duplicadas.

### Tests for User Story 2

> Escribir T030 primero y confirmar que falla por la conducta ausente.

- [X] T030 [P] [US2] Escribir los escenarios de idempotencia (misma key â†’ mismo
  run; mismo contenido distinta key â†’ sin duplicados; retry interrumpido â†’ sin
  filas duplicadas; replay terminal) en
  `tests/integration/ingestion/test_idempotency.py`

### Implementation for User Story 2

- [X] T031 [US2] Implementar la derivaciÃ³n de `batch_key` (SHA-256 del archivo
  cuando no se provee) y el reuso del run existente por identidad en
  `src/umbral/api/routers/imports.py` y `src/umbral/application/ingestion/service.py`
- [X] T032 [US2] Verificar/ajustar el handler y el modelo para que los conteos se
  deriven de filas comprometidas y el unique `(source_id, external_id,
  content_sha256)` evite duplicados ante reintentos en
  `src/umbral/workers/imports.py` y
  `src/umbral/infrastructure/db/models/imports.py`

**Checkpoint**: US1 y US2 funcionan â€” repeticiones e interrupciones no duplican
efectos.

---

## Phase 5: User Story 3 â€” Diagnosticar rechazos y evaluar la calidad del lote (Priority: P2)

**Goal**: Consultar cuarentenas y el reporte de calidad de un lote para decidir
quÃ© corregir o descartar.

**Independent Test**: el reporte del lote de referencia coincide con los conteos
reales (accepted/quarantined/duplicates/missing_fields y missing por campo), la
descarga CSV entrega el detalle por registro y el detalle de cuarentena es
consultable; acceso sin rol operador rechazado.

### Tests for User Story 3

> Escribir T033 primero y confirmar que falla por la conducta ausente.

- [X] T033 [P] [US3] Escribir los tests de quality report (conteos exactos,
  missing por campo, distribuciones anormales, descarga CSV, 409 en run no
  terminal) en `tests/integration/ingestion/test_quality_report.py` y
  `tests/unit/api/test_imports.py`

### Implementation for User Story 3

- [X] T034 [US3] Implementar el cÃ³mputo de quality (conteos, campos faltantes,
  distribuciones anormales) derivado de filas comprometidas en
  `src/umbral/application/ingestion/quality.py`
- [X] T035 [US3] Implementar `GET /api/v1/imports/runs/{run_id}/quality`,
  `.../quality/download` (CSV, `Cache-Control: no-store`) y
  `GET /api/v1/imports/quarantine/{record_id}` en
  `src/umbral/api/routers/imports.py`
- [X] T036 [US3] AÃ±adir la acciÃ³n `ops.ingestion.quality.read` y cubrir permisos
  y descarga segura en `src/umbral/domain/identity/policy.py` y
  `tests/integration/identity/test_import_authorization.py`

**Checkpoint**: US1â€“US3 funcionan â€” cuarentena y calidad consultables y
descargables con permiso de operador.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Harness propio, documentaciÃ³n operativa, evidencia y cierre de
trazabilidad.

- [X] T037 [P] AÃ±adir `scripts/check-imports.ps1` (pytest de ingestion) y
  registrarlo en `scripts/check.ps1` siguiendo el patrÃ³n de `check-jobs.ps1`
- [X] T038 [P] Documentar operaciÃ³n de importaciÃ³n, cuarentena y reintentos en
  `docs/runbooks/import-ingestion.md`
- [X] T039 Registrar la evidencia de aceptaciÃ³n (comandos, resultados, mÃ©tricas
  SC-001 a SC-009) en `docs/runbooks/evidence/bronze-ingestion-acceptance.md`
- [X] T040 Ejecutar `specs/002-bronze-ingestion/quickstart.md` de punta a punta
  y corregir cualquier desviaciÃ³n de contratos o guÃ­a
- [X] T041 [P] Verificar auditorÃ­a/telemetrÃ­a metadata-only (sin payload, sin
  rutas de archivo, sin secretos) y correlaciÃ³n runâ†’job en
  `src/umbral/application/ingestion/` y `src/umbral/workers/imports.py`
- [X] T042 Ejecutar `.\scripts\check.ps1` desde un checkout limpio y cerrar la
  trazabilidad de cada FR/SC contra su evidencia automatizada

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P1)**: depende de Foundational; no depende de US2/US3.
- **US2 (P2)**: depende de Foundational y de la captura de US1 (T021â€“T023);
  independientemente testeable despuÃ©s.
- **US3 (P2)**: depende de Foundational y del router de US1 (T026); no depende
  de US2.
- **Polish (final)**: depende de las historias deseadas.

### User Story Dependencies

- **US1**: `ImportRunService` (T017) + repos (T014/T015) + handler (T021) +
  router (T026).
- **US2**: reuse del runtime de jobs y de `ImportRunService`; agrega pruebas de
  identidad y la derivaciÃ³n de `batch_key`.
- **US3**: `ImportRunService.get` + conteos; agrega `quality.py` y endpoints de
  lectura.
- Trabajo secuencial recomendado: US1 â†’ US2 â†’ US3.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Valores/puertos antes de adapters; adapters antes de servicio; servicio antes
  de router; router antes de OpenAPI/cliente.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003 en Setup; T006/T007, T010/T014/T015 en Foundational; T019/T020/T024
  en US1; T033 en US3 â€” tocan archivos distintos sin dependencias.
- US2 y US3 pueden empezar en paralelo una vez que US1 deje el router y el
  servicio estables (si hay capacidad).
- T037â€“T042 (Polish) son mayormente paralelizables salvo T040/T042 que cierran.

---

## Parallel Example: User Story 1

```bash
# Tests de US1 en paralelo:
Task: "IntegraciÃ³n de captura completa en tests/integration/ingestion/test_capture_pipeline.py"
Task: "Unit tests del handler en tests/unit/application/ingestion/test_import_handler.py"
Task: "Tests de API/autorizaciÃ³n en tests/unit/api/test_imports.py"

# Valores y puertos en paralelo:
Task: "Valores puros en src/umbral/application/ingestion/contracts.py"
Task: "Puertos en src/umbral/application/ingestion/ports.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational â€” bloquea todo).
3. Completar Phase 3 (US1): importaciÃ³n de punta a punta con snapshots,
   cuarentena y permisos.
4. **STOP y VALIDAR** US1 con su Independent Test sobre Postgres real.
5. Demo/entrega si corresponde.

### Incremental Delivery

1. Setup + Foundational â†’ validator, adapters y persistencia listos.
2. US1 â†’ importar lote punta a punta â†’ validar â†’ demo (MVP).
3. US2 â†’ idempotencia de reintentos â†’ validar.
4. US3 â†’ reporte de calidad y cuarentena â†’ validar.
5. Polish â†’ harness, runbook y evidencia de cierre.

### Parallel Team Strategy

1. Equipo completa Setup + Foundational juntos.
2. Tras Foundational: US1 primero (bloquea demos); US2/US3 pueden repartirse
   tras dejar el router/servicio de US1 estables.
3. Las historias integran sin romperse entre sÃ­ (endpoints y tablas separados).

---

## Notes

- [P] = archivos distintos, sin dependencias de tareas incompletas.
- [Story] mapea cada tarea a su historia (`spec.md`) para trazabilidad.
- Cada historia es independientemente completa y testeable.
- Verificar que los tests fallen antes de implementar.
- Commit despuÃ©s de cada tarea o grupo lÃ³gico.
- Detenerse en cualquier checkpoint para validar la historia sola.
- Evitar: tareas vagas, conflictos de archivo, dependencias entre historias que
  rompan la independencia.

