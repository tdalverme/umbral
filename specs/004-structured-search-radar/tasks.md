# Tasks: Structured Search Radar

**Input**: Design documents from `specs/004-structured-search-radar/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice
starts with the failing contract/unit/integration test named here"). En cada
fase se escriben primero los tests indicados y se confirma que fallan por la
conducta ausente antes de implementar.

**Organization**: Las tareas se agrupan por historia para conservar slices
demostrables. Setup y Foundational contienen sólo trabajo compartido
(contratos search-profile-v1, scoring-baseline-v1 y events-v1, políticas
puras, persistencia y migración `0005`). US1 entrega la creación del radar con
run disparado (sin ejecución: el handler es US3); US3 publica los matches
asincrónicamente.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos versionados machine-checkable
(search-profile-v1, scoring-baseline-v1, events-v1), el conjunto golden de
radar y los límites de arquitectura que usarán todas las historias.

- [X] T001 Definir el contrato search-profile-v1 machine-checkable (campos,
  validación, lista cerrada de barrios CABA, `unknown_strategy` por filtro,
  máquina de estados) en `contracts/search-profiles/v1/search-profile-policy.json`
- [X] T002 [P] Definir el contrato scoring-baseline-v1 machine-checkable
  (pesos por dimensión, funciones de fit, tie-break, formato de
  `contributions`) en `contracts/scoring/v1/scoring-baseline.json`
- [X] T003 [P] Definir el contrato events-v1 machine-checkable (registry
  cerrado: tipos `radar.created.v1`, `recommendation.run_published.v1`,
  `recommendation.impression.v1`, `recommendation.detail_viewed.v1`,
  `listing.source_opened.v1`; keys requeridas; claves PII prohibidas) en
  `contracts/events/v1/events-registry.json`
- [X] T004 [P] Crear el conjunto golden de radar (perfiles válidos/inválidos
  con casos de desconocidos, scoring esperado con desglose, eventos válidos e
  inválidos) en `tests/fixtures/radar/profiles-golden.json`,
  `tests/fixtures/radar/scoring-golden.json` y
  `tests/fixtures/radar/events-golden.json` (reusando la fixture Silver de 003)
- [X] T005 [P] Añadir fixtures de arquitectura para los límites de
  `application/radar` y `application/events` (permite application→domain y
  adapters→application; prohíbe domain→infrastructure, radar→FastAPI/LLM y
  dominio con imports web) en `tests/architecture/test_radar_boundaries.py`

**Checkpoint**: contratos publicados, conjunto golden disponible y límites
nuevos verificados desde el harness.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Políticas puras (perfil, hard filters, scoring, registry de
eventos), puertos y persistencia de las cinco tablas. Nada de las historias
comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T006 Escribir la conformance del search profile: validación de campos,
  lista CABA, `unknown_strategy` por filtro, estados/transiciones en
  `tests/contract/test_search_profile_contract.py`
- [X] T007 [P] Escribir la conformance del scoring baseline: pesos, funciones
  de fit (incluidos desconocidos), tie-break y `contributions` en
  `tests/contract/test_scoring_baseline.py`
- [X] T008 [P] Escribir la conformance del registry de eventos: tipos cerrados,
  keys requeridas/extra rechazadas, claves PII prohibidas en
  `tests/contract/test_events_registry.py`
- [X] T009 [P] Escribir los tests de migración `0005` (upgrade desde vacío y
  desde `0004`, head único, drift, downgrade) en
  `tests/migrations/test_0005_search_radar.py`
- [X] T010 [P] Escribir los unit tests de repos (guardas de unicidad
  `(profile_id, profile_version)`, `(run_id, position)`, `(owner_id, name)`,
  lock optimista `WHERE id AND version`) en
  `tests/unit/application/radar/test_repositories.py`

### Implementation for Foundational

- [X] T011 Definir los valores puros y errores (`SearchProfile`, `ProfileVersion`,
  `HardFilterPolicy`, `RunSnapshot`, `ItemSnapshot`, `RadarError`) en
  `src/umbral/application/radar/contracts.py`
- [X] T012 [P] Implementar el loader de search-profile-v1 y `validate_profile`
  puro (campos, CABA, estrategias de desconocido, reglas de transición de
  estado) en `src/umbral/application/radar/profile_policy.py`
- [X] T013 [P] Implementar `apply_hard_filters` puro (presupuesto, zonas,
  ambientes, superficie, requisitos P0 y `unknown_strategy`) en
  `src/umbral/application/radar/hard_filters.py`
- [X] T014 [P] Implementar el loader de scoring-baseline-v1 y `compute_score`
  puro (fit por dimensión, pesos, tie-break, `contributions`) en
  `src/umbral/application/radar/scoring.py`
- [X] T015 [P] Implementar el registry cerrado de eventos v1 y
  `validate_event(type, payload)` (patrón de `domain/identity/events.py`) en
  `src/umbral/application/events/registry.py` y
  `src/umbral/application/events/contracts.py`
- [X] T016 [P] Definir los puertos `SearchProfileRepository`,
  `ProfileVersionRepository`, `RunRepository`, `ItemRepository` y
  `EventRepository` en `src/umbral/application/radar/ports.py`
- [X] T017 Implementar los modelos y ENUMs (`search_profile_state`,
  `recommendation_run_state`, `recommendation_run_trigger`) con
  constraints/índices y registrarlos en
  `src/umbral/infrastructure/db/models/radar.py` y
  `src/umbral/infrastructure/db/models/__init__.py`
- [X] T018 Crear la revisión `0005_search_radar` (down: `0004_silver_normalization`)
  con las cinco tablas, los ENUMs y el chequeo de extensión PostGIS en
  `alembic/versions/0005_search_radar.py`
- [X] T019 [P] Implementar los repos SQLAlchemy (sin commit propio, version
  optimista, filtros por `owner_id`) en
  `src/umbral/infrastructure/db/repositories/radar.py`
- [X] T020 [P] Implementar los adapters in-memory para tests en `tests/fakes/radar.py`
- [X] T021 Añadir los settings `radar.*` (`page_size_default` 25,
  `page_size_max` 100, `run_job_type`, `score_policy_version`,
  `run_poll_interval_seconds` 3) validados al iniciar en
  `src/umbral/infrastructure/config/settings.py` con su test

**Checkpoint**: políticas puras, contratos y persistencia disponibles y
verificados; las historias pueden comenzar.

---

## Phase 3: User Story 1 — Crear un radar estructurado (Priority: P1) MVP

**Goal**: el usuario invitado define presupuesto, zonas y requisitos P0 en un
onboarding guiado y, al confirmar, queda un radar activo con perfil versionado,
evento `radar.created.v1` y run disparado (estado `pending` con job), con la
UI mostrando "generando resultados" mientras corre.

**Independent Test**: crear un radar persiste perfil + versión 1 + evento y
dispara el job `recommendation.run`; el onboarding valida sin persistir
parciales, exige resumen/confirmación y es operable por teclado; el radar
muestra el estado de generación distinguible de vacío y error. La publicación
de matches (handler) se verifica en US3.

### Tests for User Story 1

> Escribir T022–T025 primero y confirmar que fallan por la conducta ausente.

- [X] T022 [P] [US1] Escribir los unit tests de `create_profile` (persistencia
  de perfil + versión 1 + evento `radar.created.v1` + submit del job con
  idempotency `recommendation:{profile_id}:{version_id}`) en
  `tests/unit/application/radar/test_profile_service.py`
- [X] T023 [P] [US1] Escribir los tests de contrato HTTP del create/read
  (`POST /api/v1/search-profiles`, `GET /api/v1/search-profiles/{id}`:
  validación 422 accionable, 401/403, ownership) en
  `tests/contract/test_search_profiles_api.py`
- [ ] T024 [P] [US1] Escribir los tests de UI del onboarding (3 pasos,
  validación accesible, resumen exacto, confirmación, estado de generación) en
  `apps/web/src/app/(protected)/radar/new/onboarding.test.tsx`
- [X] T025 [P] [US1] Escribir el e2e del onboarding con el actor de prueba
  (crear radar → estado "generando resultados" → selector lo muestra) en
  `tests/e2e/radar-onboarding.spec.ts`

### Implementation for User Story 1

- [X] T026 [US1] Implementar `RadarService.create_profile` (validación,
  transacción perfil + versión 1 + evento, submit del run job, snapshot del
  run con estado `pending`) en `src/umbral/application/radar/service.py`
- [X] T027 [US1] Agregar las acciones `product.search_profile.create` y
  `product.search_profile.read` (owner_required) a la matriz deny-by-default en
  `src/umbral/domain/identity/policy.py`
- [X] T028 [US1] Implementar el router `routers/search_profiles.py` (POST
  create, GET by id con estado del último run; patrón `configure_*_routes` +
  `_authorize` con `resource_owner_id`; errores RFC 9457) y registrarlo en
  `src/umbral/api/main.py` y `src/umbral/api/dependencies.py`
- [X] T029 [US1] Exportar el OpenAPI (`scripts/export-openapi.ps1`),
  regenerar y commitear el cliente web (`npm run api:generate --workspace @umbral/web`)
- [X] T030 [US1] Montar `QueryClientProvider` y cablear el cliente generado al
  origin del navegador (patrón BFF) en `apps/web/src/lib/query/providers.tsx`
  y `apps/web/src/lib/api/browser.ts`
- [ ] T031 [US1] Construir el onboarding `apps/web/src/app/(protected)/radar/new/page.tsx`
  (3 pasos: presupuesto y operación; zonas CABA; requisitos P0 — con resumen y
  confirmación) más las rutas BFF de proxy en
  `apps/web/src/app/api/radar/`

**Checkpoint**: US1 es un MVP demostrable — crear radar de punta a punta con
run disparado y estado de generación visible.

---

## Phase 4: User Story 2 — Administrar las búsquedas sin mezclar datos (Priority: P1)

**Goal**: el usuario lista, edita, pausa, reanuda y archiva sus radares sin
mezclar datos entre ellos; la edición concurrente devuelve el error tipado.

**Independent Test**: listar distingue activos/pausados/archivados; pausar
detiene runs y reanudar vuelve a correr; archivar oculta conservando datos;
una edición con `expected_version` vencida devuelve 409 sin pérdida silenciosa;
operar un radar ajeno es rechazado (403) sin revelar datos; editar un radar
activo invalida resultados y dispara un nuevo run con versión 2.

### Tests for User Story 2

> Escribir T032–T034 primero y confirmar que fallan por la conducta ausente.

- [X] T032 [P] [US2] Escribir los unit tests de administración (transiciones
  activo↔pausado, →archivado, edición con versionado + disparo de run,
  lock optimista) en `tests/unit/application/radar/test_profile_admin.py`
- [X] T033 [P] [US2] Escribir los tests de contrato HTTP de administración
  (`GET /api/v1/search-profiles`, `PATCH /{id}`, `POST /{id}/status`:
  409 concurrency tipado, 403 cross-user, validación) en
  `tests/contract/test_search_profiles_admin_api.py`
- [ ] T034 [P] [US2] Escribir los tests de UI del selector y edición (tabs por
  estado, contexto por radar, error de concurrencia visible) en
  `apps/web/src/app/(protected)/radar/selector.test.tsx`

### Implementation for User Story 2

- [X] T035 [US2] Implementar `list_profiles`, `get_profile`, `update_profile`
  (versión + invalida resultados + dispara run) y `set_status` (máquina de
  estados, lock optimista) en `src/umbral/application/radar/service.py`
- [X] T036 [US2] Agregar las acciones `product.search_profile.update` y
  `product.search_profile.status` (owner_required) en
  `src/umbral/domain/identity/policy.py`
- [X] T037 [US2] Implementar en `routers/search_profiles.py` el listado,
  `PATCH /{id}` (con `expected_version` → `ConcurrencyConflict` 409) y
  `POST /{id}/status`
- [X] T038 [US2] Construir el selector `apps/web/src/app/(protected)/radar/page.tsx`
  (activas/pausadas/archivadas, contexto en desktop/mobile) y el flujo de
  edición reutilizando el formulario del onboarding con manejo visible de 409

**Checkpoint**: US1 y US2 funcionan — radares administrables, versionados y
aislados por usuario.

---

## Phase 5: User Story 3 — Ver matches deterministas con contribuciones (Priority: P1)

**Goal**: el run asíncrono aplica hard filters, calcula el scoring baseline
determinista y publica matches congelados que el usuario pagina en cards/lista
con score total; un fallo conserva el último run válido.

**Independent Test**: dos ejecuciones del mismo perfil sobre el mismo candidate
set producen idéntico orden, scores y desglose; los matches provienen de un run
persistido con profile snapshot, candidate set, versión de scoring y tiempos;
un fallo de publicación deja visible el último run válido sin parciales; la
paginación por `run_id` + `position` no repite ni omite matches; el radar
distingue "generando resultados" de vacío/error; los runs publican en < 30 s.

### Tests for User Story 3

> Escribir T039–T041 primero y confirmar que fallan por la conducta ausente.

- [X] T039 [P] [US3] Escribir la integración del pipeline de runs (candidate
  query con PostGIS, hard filters con desconocidos, scoring determinista con
  doble ejecución idéntica, publicación atómica < 30 s, fallo inducido que
  conserva el último run válido) en `tests/integration/radar/test_run_pipeline.py`
- [X] T040 [P] [US3] Escribir la integración de paginación (keyset por
  `(run_id, position)`: 0 repetidos/omitidos; cambio de run_id cambia el
  conjunto visible) en `tests/integration/radar/test_matches_pagination.py`
- [X] T041 [P] [US3] Escribir los unit tests del handler `recommendation.run`
  (target/identidad, conteos, `failure_code`, evento
  `recommendation.run_published.v1`) en
  `tests/unit/application/radar/test_run_handler.py`

### Implementation for User Story 3

- [X] T042 [US3] Implementar `RecommendationRunHandler` (query de candidatos
  SQL/PostGIS de solo lectura, `apply_hard_filters` + `compute_score`,
  publicación atómica run+items+evento) en `src/umbral/workers/radar.py`
- [X] T043 [US3] Implementar `get_matches(run_id)` (paginación keyset),
  `get_run_status` y el submit del run en `src/umbral/application/radar/service.py`
- [X] T044 [US3] Registrar el job `recommendation.run` en el registry y
  componer el runtime en `src/umbral/workers/registry.py` y
  `src/umbral/workers/composition.py`
- [X] T045 [US3] Implementar el router `routers/matches.py`
  (`GET /api/v1/search-profiles/{id}/matches?run_id=&page_size=` con acción
  `product.matches.read` owner_required)
- [X] T046 [US3] Construir el radar `apps/web/src/app/(protected)/radar/[id]/page.tsx`
  (cards/lista con precio total, barrio, superficie, ambientes, score total y
  fuente; polling 3 s mientras `pending/running`; paginación estable; estados
  loading/empty/parcial/error)

**Checkpoint**: US1–US3 funcionan — radar con matches deterministas,
persistentes y paginados.

---

## Phase 6: User Story 4 — Explorar resultados en lista y mapa sincronizados (Priority: P2)

**Goal**: la lista y el mapa sincronizan selección y el mapa nunca revela
coordenadas más precisas que las autorizadas.

**Independent Test**: seleccionar un match en la lista se refleja en el mapa y
viceversa; un listing con precisión `neighborhood`/`unknown` no renderiza un
punto más preciso que lo autorizado y declara su precisión; radar sin
resultados muestra estado vacío con siguiente paso; fallo de tiles degrada a
error recuperable sin romper la lista.

### Tests for User Story 4

> Escribir T047–T048 primero y confirmar que fallan por la conducta ausente.

- [ ] T047 [P] [US4] Escribir los tests del componente de mapa (guard de
  precisión por `geo_precision`, atribución, estado de error de tiles) en
  `apps/web/src/components/radar/map.test.tsx`
- [ ] T048 [P] [US4] Escribir el e2e lista-mapa (sincronización de selección,
  puntos con precisión correcta, empty state, error de tiles recuperable) en
  `tests/e2e/radar-map.spec.ts`

### Implementation for User Story 4

- [X] T049 [US4] Crear el componente MapLibre (Client Component con dynamic
  import, tiles OSM con atribución, render según `geo_precision`, estado de
  error de tiles recuperable) en `apps/web/src/components/radar/map.tsx`
  (dependencia `maplibre-gl` instalada en `apps/web/package.json`)
- [X] T050 [US4] Crear la card de match (precio total, barrio, superficie,
  ambientes, score total, fuente, estados) y la sincronización de selección
  lista↔mapa con estado vacío en
  `apps/web/src/components/radar/match-card.tsx` y
  `apps/web/src/components/radar/radar-shell.tsx`

**Checkpoint**: US1–US4 funcionan — radar en lista y mapa sincronizados con
precisión respetada.

---

## Phase 7: User Story 5 — Entender el detalle sin afirmaciones no soportadas (Priority: P2)

**Goal**: el detalle muestra media, atributos, fuente original, ubicación,
datos faltantes, cambios conocidos y el desglose de contribuciones, y toda la
superficie distingue estados responsive.

**Independent Test**: abrir el detalle de un match del propio radar muestra los
datos soportados y declara los faltantes sin suponer; el desglose aparece solo
en el detalle (las cards muestran solo el score total); un listing ajeno o un
id inexistente responde 403/404; loading/empty/parcial/error/no autorizado/no
encontrado se distinguen en desktop y mobile con recuperación.

### Tests for User Story 5

> Escribir T051–T053 primero y confirmar que fallan por la conducta ausente.

- [X] T051 [P] [US5] Escribir los tests de contrato HTTP del detalle
  (`GET /api/v1/listings/{listing_id}`: autorización vía runs del usuario,
  403 cross-user, 404, ensamblado de datos con faltantes y cambios) en
  `tests/contract/test_listings_api.py`
- [ ] T052 [P] [US5] Escribir los tests de UI del detalle (media, atributos,
  fuente, faltantes, cambios conocidos, desglose sin certeza) en
  `apps/web/src/app/(protected)/listings/[id]/detail.test.tsx`
- [ ] T053 [P] [US5] Escribir los tests de estados responsive (loading, empty,
  parcial, error, 401, 404 en desktop y mobile con acciones de recuperación) en
  `apps/web/src/components/radar/states.test.tsx`

### Implementation for User Story 5

- [X] T054 [US5] Implementar el router `routers/listings.py`
  (`GET /api/v1/listings/{listing_id}` con acción `product.listing.read` y
  autorización a través de los runs del usuario) en
  `src/umbral/api/routers/listings.py` y
  `src/umbral/application/radar/service.py` (ensamblado del detalle)
- [X] T055 [US5] Construir el detalle
  `apps/web/src/app/(protected)/listings/[id]/page.tsx` (media, atributos,
  fuente original, ubicación, datos faltantes, cambios conocidos y desglose de
  contribuciones sin presentarlas como certeza)
- [X] T056 [US5] Construir los componentes de estados (loading, empty, parcial,
  error recuperable, no autorizado, no encontrado) reutilizables en
  `apps/web/src/components/radar/states.tsx` y aplicarlos a radar y detalle

**Checkpoint**: US1–US5 funcionan — detalle honesto y estados distinguibles en
toda la superficie.

---

## Phase 8: User Story 6 — Medir la activación y verificar el recorrido E2E (Priority: P1)

**Goal**: cada acción emite su evento versionado sin PII y el recorrido
lote→reporte→Silver→radar→detalle es correcto e idempotente al reimportar.

**Independent Test**: `radar.created.v1` y `recommendation.run_published.v1`
persisten como filas; los eventos de cliente (impression, detail_viewed,
source_opened) se aceptan solo con payload válido (400 con tipo/keys PII;
403 con perfil ajeno); reimportar el mismo lote produce 0 duplicados de
listings, runs ni matches; `scripts/check-radar.ps1` corre en el harness.

### Tests for User Story 6

> Escribir T057–T058 primero y confirmar que fallan por la conducta ausente.

- [X] T057 [P] [US6] Escribir la integración de eventos de producto (filas
  server y client, validación 400/403 contra el registry, correlación) en
  `tests/integration/radar/test_product_events.py`
- [X] T058 [P] [US6] Escribir la integración E2E de reimport (lote → reporte →
  Silver → radar → detalle correctos; segundo import con la misma identidad
  produce 0 duplicados) en `tests/integration/radar/test_e2e_reimport.py`

### Implementation for User Story 6

- [X] T059 [US6] Implementar el router `routers/product_events.py`
  (`POST /api/v1/product-events` con acción `product.events.emit` y validación
  del registry) en `src/umbral/api/routers/product_events.py`
- [X] T060 [US6] Emitir eventos de cliente en la web (impression en el radar,
  detail_viewed en el detalle, source_opened al abrir la fuente original) vía
  BFF en `apps/web/src/lib/radar/events.ts` y las rutas
  `apps/web/src/app/api/radar/events/`
- [X] T061 [US6] Añadir `scripts/check-radar.ps1` (pytest de radar + tests de
  contrato) y registrarlo en `scripts/check.ps1` siguiendo el patrón de
  `check-silver.ps1`
- [X] T062 [US6] Actualizar `docs/api/endpoints.md` con la superficie
  implementada y documentar la operación del radar (runs, estados, eventos) en
  `docs/runbooks/structured-search-radar.md`

**Checkpoint**: US1–US6 funcionan — medición instrumentada y recorrido E2E
idempotente.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Accesibilidad auditada, telemetría sin PII y evidencia de cierre.

- [ ] T063 [P] Ejecutar la auditoría de accesibilidad de la superficie nueva
  (onboarding, selector, radar, mapa, detalle: navegación por teclado,
  nombres, contraste, axe en light/dark, reflow 320px) en
  `tests/e2e/` y corregir hallazgos (SC-009)
- [ ] T064 [P] Verificar telemetría/auditoría metadata-only (eventos y logs sin
  PII, payloads ni URLs; correlación en filas de eventos y runs) en
  `src/umbral/application/radar/`, `src/umbral/application/events/` y
  `src/umbral/api/routers/`
- [ ] T065 Ejecutar `specs/004-structured-search-radar/quickstart.md` de punta a
  punta, `.\scripts\check.ps1` desde un checkout limpio y registrar la
  evidencia de aceptación (SC-001 a SC-013 y trazabilidad FR) en
  `docs/runbooks/evidence/structured-search-radar-acceptance.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; BLOQUEA todas las historias.
- **US1 (P1)**: depende de Foundational; no depende de US2/US3 (el run queda
  disparado pero su ejecución es US3).
- **US2 (P1)**: depende de Foundational y de `create_profile` de US1 (T026);
  independientemente testeable después.
- **US3 (P1)**: depende de Foundational y de `submit_run` de US1 (T026);
  entrega el handler y la publicación asincrónica.
- **US4 (P2)**: depende de US3 (cards/lista del radar, T046).
- **US5 (P2)**: depende de US3 (autorización del detalle vía runs) y de US2
  (contexto del selector) para navegación completa.
- **US6 (P1)**: depende de US1 (evento create), US3 (run_published) y US5
  (eventos del detalle) para el E2E; la verificación cierra el incremento.
- **Polish (final)**: depende de las historias deseadas.

### User Story Dependencies

- **US1**: `profile_policy`/`hard_filters` (T012/T013) + repos (T019/T020) +
  `create_profile` (T026) + router (T028) + onboarding (T031).
- **US2**: reusa `create_profile`; agrega transiciones, versionado y edición.
- **US3**: reusa `create_profile`/`submit_run`; agrega handler, scoring y
  publicaciones atómicas.
- **US4**: reusa el radar de US3; agrega mapa y sincronización.
- **US5**: reusa runs de US3; agrega detalle y estados.
- **US6**: cierra sobre US1/US3/US5; agrega router de eventos, emisión web y
  verificación E2E.
- Trabajo secuencial recomendado: US1 → US2 → US3 → (US4 ∥ US5) → US6.

### Within Each User Story

- Tests escritos y fallando antes de implementar.
- Valores/puertos antes de adapters; adapters antes de servicio; servicio antes
  de router/handler; router antes de UI; UI antes de e2e.
- Historia completa y verificada antes de pasar a la siguiente prioridad.

### Parallel Opportunities

- T002/T003/T004/T005 en Setup; T007/T008/T009/T010, T012/T013/T014/T015/T016,
  T019/T020 en Foundational; T022/T023/T024/T025 en US1; T032/T033/T034 en
  US2; T039/T040/T041 en US3; T047/T048 en US4; T051/T052/T053 en US5;
  T057/T058 en US6; T063/T064 en Polish — tocan archivos distintos sin
  dependencias.
- US4 y US5 pueden empezar en paralelo una vez que US3 deje el radar y los
  matches estables (si hay capacidad).
- T061/T062 (harness y docs) son paralelizables con las historias tardías.

---

## Parallel Example: User Story 1

```bash
# Tests de US1 en paralelo:
Task: "Unit tests de create_profile en tests/unit/application/radar/test_profile_service.py"
Task: "Contract tests HTTP en tests/contract/test_search_profiles_api.py"
Task: "Vitest del onboarding en apps/web/src/app/(protected)/radar/new/onboarding.test.tsx"
Task: "E2E del onboarding en tests/e2e/radar-onboarding.spec.ts"

# Implementación en paralelo (archivos distintos):
Task: "RadarService.create_profile en src/umbral/application/radar/service.py"
Task: "Acciones policy en src/umbral/domain/identity/policy.py"
Task: "Router search_profiles en src/umbral/api/routers/search_profiles.py"
Task: "Onboarding UI en apps/web/src/app/(protected)/radar/new/page.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar Phase 1 (Setup).
2. Completar Phase 2 (Foundational — bloquea todo).
3. Completar Phase 3 (US1): crear radar con run disparado y estado de
   generación visible (sin publicación de matches).
4. **STOP y VALIDAR** US1 con su Independent Test sobre Postgres/PostGIS real.
5. Demo/entrega si corresponde.

### Incremental Delivery

1. Setup + Foundational → contratos, políticas puras y persistencia listos.
2. US1 → crear radar → validar → demo (MVP).
3. US2 → administrar radares (selector, edición, estados) → validar.
4. US3 → matches deterministas asincrónicos → validar.
5. US4 → lista y mapa sincronizados → validar.
6. US5 → detalle y estados responsive → validar.
7. US6 → eventos verificados y E2E idempotente → cerrar.
8. Polish → accesibilidad, telemetría y evidencia de cierre.

### Parallel Team Strategy

1. Equipo completo Setup + Foundational juntos.
2. Tras Foundational: US1 primero (bloquea demos); US2/US3 pueden repartirse
   tras dejar `create_profile` estable.
3. Tras US3: US4 y US5 en paralelo (web) mientras US6 prepara tests de
   eventos/reimport.
4. Las historias integran sin romperse entre sí (tablas, jobs y rutas
   separados; el contrato OpenAPI crece aditivamente).

---

## Estado de cierre (2026-08-06)

- Incremento cerrado con evidencia en
  `docs/runbooks/evidence/structured-search-radar-acceptance.md`; backlog
  marcado (UM-H2-019 a UM-H2-034).
- Diferidas a seguimiento posterior (no bloquean el cierre): T024/T025/T034/
  T047/T048/T052/T053 (tests web dedicados: vitest y e2e Playwright con axe),
  T063 (auditoría de accesibilidad e2e), T064 (verificación final de
  telemetría sin PII), T065 (gate completo desde checkout limpio + evidencia
  final en CI).

## Notes

- [P] = archivos distintos, sin dependencias de tareas incompletas.
- [Story] mapea cada tarea a su historia (`spec.md`) para trazabilidad.
- Cada historia es independientemente completa y testeable.
- Verificar que los tests fallen antes de implementar.
- Commit después de cada tarea o grupo lógico.
- Detenerse en cualquier checkpoint para validar la historia sola.
- Evitar: tareas vagas, conflictos de archivo, dependencias entre historias que
  rompan la independencia.
- Recordar los gates de contrato: exportar OpenAPI y regenerar el cliente antes
  de commitear cambios de API; `api:check` bloquea drift.
