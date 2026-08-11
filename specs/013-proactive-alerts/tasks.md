# Tasks: Notificaciones y alertas proactivas

**Input**: Design documents from `specs/013-proactive-alerts/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: Slices test-first; en cada fase se escriben primero los
contract/unit tests indicados y se confirma que fallan por la conducta
ausente antes de implementar.

**Organization**: Las tareas se agrupan por historia de `spec.md`
conservando los slices del plan (Phase A..F). Setup publica los contratos
`notifications/v1` (policy + planner golden), los +6 eventos de registry y
los settings `NOTIFICATIONS_*`; Foundational publica los parsers puros y la
capa de datos (migracion `0013`); US1 preferencias versionadas y
configurables; US2 planner deterministico con gate golden; US3 duties de
plan/digest + job de entrega + adapter email; US4 inbox web (API + centro);
US5 baja desde email; US6 operacion, instrumentacion y E2E; Polish el
harness `check-alerts.ps1`, la arquitectura de capas y el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos machine-checkable de notificaciones, los
+6 eventos y los settings que usaran todas las historias.

- [ ] T001 [P] Publicar la politica de notificacion versionada e inmutable:
  `immediate_score_threshold`, `fatigue_cooldown_hours` (6),
  `fatigue_window_hours` (24), `digest_default_local_hour` (9),
  `digest_max_items` (10), `quiet_hours_default` (22:00-08:00) en
  `contracts/notifications/v1/notification-policy-v1.json`
- [ ] T002 [P] Publicar el dataset golden del planner: casos por familia
  (`new_match_immediate`, `new_match_digest`, `price_drop`, `duplicate`,
  `quiet_hours`, `fatigue`, `digest_group`, `discarded`) con `item`,
  `history`, `preferences`, `policy` y `expected` (trigger, reason_code,
  decision_state), `reviewed_by`/`reviewed_at` y 0 PII en
  `contracts/notifications/v1/planner-golden-v1.json`
- [ ] T003 [P] Agregar los 6 eventos al registry cerrado: `decision_created`,
  `delivered`, `delivery_failed`, `viewed`, `acted`, `unsubscribed` (namespace
  `notification`, version `.v1`) con payloads sin PII en
  `contracts/events/v1/events-registry.json`
- [ ] T004 [P] Agregar los settings `NOTIFICATIONS_ENABLED`,
  `NOTIFICATIONS_POLICY_VERSION`, `NOTIFICATIONS_PLANNER_DATASET_VERSION`,
  `NOTIFICATIONS_EMAIL_FROM`, `NOTIFICATIONS_PLAN_JOB_TYPE`,
  `NOTIFICATIONS_DIGEST_JOB_TYPE`, `NOTIFICATIONS_DELIVER_JOB_TYPE`,
  `NOTIFICATIONS_UNSUBSCRIBE_TTL_HOURS`,
  `NOTIFICATIONS_DEFAULT_TIMEZONE` al inventario cerrado de
  `src/umbral/infrastructure/config/settings.py` (campos + `_known_fields`)

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Parsers puros de los contratos y la capa de datos (migracion
`0013`) que bloquean todas las historias.

### Tests for Foundational

- [ ] T005 [P] Escribir contract tests de la politica: version requerida,
  umbrales no negativos, horas validas, 0 PII en
  `tests/contract/test_notifications_policy.py`
- [ ] T006 [P] Escribir contract tests del planner golden: registry version,
  familias conocidas, casos con `expected` completo, casos cubren >=1 por
  familia y referencias de revision en
  `tests/contract/test_notifications_planner_golden.py`
- [ ] T007 [P] Escribir tests de la migracion `0013` up/down y del inventario
  cerrado en `tests/migrations/test_0013_notifications.py`

### Implementation for Foundational

- [ ] T008 [P] Implementar el parser puro de la politica en
  `src/umbral/application/notifications/policy.py` (dataclasses + errores
  tipados; 0 dependencias de infra)
- [ ] T009 [P] Implementar el parser puro del dataset golden del planner en
  `src/umbral/application/notifications/planner_golden.py`
- [ ] T010 [P] Implementar la migracion `0013_notifications` con las 3
  tablas (`notification_preferences`, `notification_decisions` con indice
  unico parcial `(recommendation_item_id, trigger)` para 0 duplicados,
  `notification_inbox_items`) en `alembic/versions/0013_notifications.py` y
  actualizar el inventario de `scripts/check-migrations.ps1`
- [ ] T011 [P] Implementar los repos SQLAlchemy (preferences, decisions,
  inbox) con ownership estricto en
  `src/umbral/infrastructure/notifications/repositories.py`

## Phase 3: US1 - Preferencias de alertas configurables (Priority: P0)

**Purpose**: Preferencias versionadas por usuario/busqueda y su
configuracion web (UM-H5-001/002).

**Independent Test**: un usuario configura canales/timezone/quiet hours/
digest/umbral y el bump de version es consultable; el planner usa la ultima
version.

### Tests for US1

- [ ] T012 [US1] Escribir unit tests del modelo de preferencias:
  validacion de zoneinfo, quiet hours (start<end), umbral 0..1, bump de
  version y estados en
  `tests/unit/application/notifications/test_preferences.py`
- [ ] T013 [US1] Escribir tests del repo de preferencias (insert/update
  versiona, ownership) en
  `tests/integration/notifications/test_preferences_repository.py`

### Implementation for US1

- [ ] T014 [US1] Implementar `application/notifications/preferences.py`
  (modelo puro, reglas de validacion, `bump_version`, defaults) y los
  contratos tipados en `application/notifications/contracts.py`
- [ ] T015 [US1] Implementar el puerto `PreferenceRepository` en
  `application/notifications/ports.py`
- [ ] T016 [US1] Implementar el servicio de preferencias (leer/actualizar con
  versionado y eventos de cambio) en
  `application/notifications/preferences_service.py`
- [ ] T017 [US1] Implementar el router GET/PUT de preferencias con ownership
  y errores tipados en `src/umbral/api/routers/notifications.py` (montar en
  `src/umbral/api/main.py`) con accion `product.notifications.preferences.*`
- [ ] T018 [US1] Implementar la configuracion de alertas en la web
  (formulario shadcn con explicacion de impacto y desactivacion) en
  `apps/web` (pagina/section de preferencias + BFF)

## Phase 4: US2 - Planner deterministico (Priority: P0)

**Purpose**: `PlanNotifications` puro con triggers, dedupe, quiet hours,
fatiga y cadencia hibrida (UM-H5-003..010), gated por dataset golden.

**Independent Test**: el gate golden (misma entrada -> misma decision y
razon); 0 duplicados; quiet hours pospone; fatiga aplica cooldown; cadencia
hibrida (immediate vs digest).

### Tests for US2

- [ ] T019 [US2] Escribir unit tests del planner contra el dataset golden
  (cada caso -> decision esperada) en
  `tests/unit/application/notifications/test_planner_golden.py`
- [ ] T020 [US2] Escribir unit tests de triggers (new_match sobre umbral,
  price_drop confirmado con umbral), dedupe, quiet hours (zoneinfo),
  fatiga (cooldown por ventana) y cadencia en
  `tests/unit/application/notifications/test_planner.py`

### Implementation for US2

- [ ] T021 [US2] Implementar `application/notifications/planner.py`:
  `PlanNotifications(items, history, prefs, policy, now)` puro que devuelve
  decisiones con trigger, reason_code y decision_state; 0 red/DB/LLM
- [ ] T022 [US2] Implementar el servicio `DecisionRepository` y la logica de
  persistencia idempotente (dedupe por item+trigger) en
  `application/notifications/decision_service.py` +
  `infrastructure/notifications/repositories.py`
- [ ] T023 [US2] Emitir `notification.decision_created.v1` al persistir una
  decision (0 PII) via el events registry

## Phase 5: US3 - Entrega confiable por email (Priority: P0)

**Purpose**: Duties de plan/digest + job de entrega idempotente + adapter
email grounded (UM-H5-011..014).

**Independent Test**: fallos simulados de proveedor -> 0 perdidas y 0
duplicados; quiet hours respetadas; digest agrupa sin alterar scores.

### Tests for US3

- [ ] T024 [US3] Escribir tests del adapter email (recording y resend):
  la redaccion recibe solo campos de la decision; clasificacion de errores en
  `tests/unit/infrastructure/notifications/test_email_adapter.py`
- [ ] T025 [US3] Escribir tests de integracion de la entrega: decision + job
  atomicos, worker idempotente con provider message id, reclaim tras fallo,
  dead-letter, en
  `tests/integration/notifications/test_delivery.py`
- [ ] T026 [US3] Escribir tests del duty de digest: agrupa pending_digest del
  dia sin alterar scores y cada decision pasa a pending_delivery una sola vez
  en `tests/integration/notifications/test_digest.py`

### Implementation for US3

- [ ] T027 [US3] Implementar el adapter email compartiendo el cliente Resend
  (mismo `RESEND_API_KEY`, sender `NOTIFICATIONS_EMAIL_FROM`, fake recording
  local) en `src/umbral/infrastructure/notifications/email_adapter.py` y su
  puerto en `application/notifications/ports.py`
- [ ] T028 [US3] Implementar el duty `notifications.plan` (procesa items
  nuevos del ultimo run publicado por busqueda con limite) en
  `src/umbral/workers/notifications.py`
- [ ] T029 [US3] Implementar el duty `notifications.digest` (agrupa y
  materializa pending_digest) en `src/umbral/workers/notifications.py`
- [ ] T030 [US3] Implementar el job `notifications.deliver` (entrega una
  decision con lease del runtime y provider message id) en
  `src/umbral/workers/notifications.py`
- [ ] T031 [P] [US3] Registrar los duties y el job en
  `src/umbral/workers/registry.py` y componerlos en
  `src/umbral/workers/composition.py` (0 imports dinamicos)
- [ ] T032 [US3] Implementar el template de email grounded (oportunidad,
  razones, riesgos, fuente, CTA, baja) alimentado solo por la decision en
  `src/umbral/infrastructure/notifications/templates.py`

## Phase 6: US4 - Centro de notificaciones web (Priority: P0)

**Purpose**: Inbox web con la misma fuente de verdad que el email
(UM-H5-015/016).

**Independent Test**: el centro muestra las mismas decisiones que el email;
mark read persiste y emite `notification.viewed.v1`; empty/error accesibles.

### Tests for US4

- [ ] T033 [US4] Escribir tests del inbox API: listado paginado con ownership,
  mark read, 404 tipificado en
  `tests/integration/notifications/test_inbox_api.py`
- [ ] T034 [US4] Escribir vitest de la pagina del centro (estados empty/
  loading/error, mark read) en `apps/web` (convencion H2.3)

### Implementation for US4

- [ ] T035 [US4] Implementar el router GET/PATCH del inbox con paginacion
  estable y ownership en `src/umbral/api/routers/notifications.py`
- [ ] T036 [US4] Implementar `NotificationInboxService` (listar, marcar
  leida, emitir `notification.viewed.v1`) en
  `application/notifications/inbox_service.py`
- [ ] T037 [US4] Implementar la pagina del centro de notificaciones (lista
  con razon, estados, enlace al contexto) + badge en el header en `apps/web`
  (BFF + vitest)

## Phase 7: US5 - Baja y control desde email (Priority: P0)

**Purpose**: Token HMAC expirable que desactiva sin login y audita
(UM-H5-017).

**Independent Test**: token valido desactiva sin login y emite el evento; un
token vencido o reutilizado es rechazado con 0 cambios.

### Tests for US5

- [ ] T038 [US5] Escribir unit tests del token: firma/verificacion, TTL,
  invalidez por version cambiada en
  `tests/unit/application/notifications/test_unsubscribe_token.py`
- [ ] T039 [US5] Escribir tests del endpoint de baja (valido, vencido,
  reutilizado) en `tests/integration/notifications/test_unsubscribe_api.py`

### Implementation for US5

- [ ] T040 [US5] Implementar `unsubscribe_token` (HMAC-SHA256 con
  user_id|search_profile_id|preferences_version|exp, TTL
  `NOTIFICATIONS_UNSUBSCRIBE_TTL_HOURS`) en
  `application/notifications/preferences.py`
- [ ] T041 [US5] Implementar el endpoint POST de baja (sin login) que
  valida, actualiza preferencias, emite `notification.unsubscribed.v1` y
  errores tipados `token_invalid`/`token_expired` en
  `src/umbral/api/routers/notifications.py`
- [ ] T042 [US5] Incluir el enlace de baja firmado en el template de email
  de `src/umbral/infrastructure/notifications/templates.py`

## Phase 8: US6 - Operacion y medicion (Priority: P0)

**Purpose**: Fallos/reintentos operativos visibles, instrumentacion de
entrega/vista/accion y E2E de alertas (UM-H5-018..020).

**Independent Test**: eventos viewed/acted alimentan precision percibida; el
operador ve backlog/causa/intentos; E2E de alertas cumple las decisiones.

### Tests for US6

- [ ] T043 [US6] Escribir tests de los eventos `notification.*.v1`: payloads
  sin PII y con los campos del contrato en
  `tests/contract/test_notification_events.py`
- [ ] T044 [US6] Escribir el E2E de alertas (new match, price drop, quiet
  hours, duplicado, fatiga, baja, fallo de proveedor) en
  `tests/integration/notifications/test_alerts_e2e.py`

### Implementation for US6

- [ ] T045 [US6] Emitir `notification.delivered.v1`/`delivery_failed.v1` en
  el job de entrega y `viewed`/`acted` en inbox/CTA en
  `src/umbral/workers/notifications.py` y
  `application/notifications/inbox_service.py`
- [ ] T046 [US6] Exponer fallos/reintentos del runtime de jobs al operador
  (vista operativa minima sin reenviar duplicados) en la consola/superficie
  operativa existente
- [ ] T047 [US6] Implementar el E2E de alertas verificando 0 duplicados, 0
  entregas fuera de quiet hours y precision percibida instrumentable

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Harness `check-alerts.ps1`, arquitectura de capas, evidencia y
cierre del hito H5.

- [ ] T048 [P] Crear `scripts/check-alerts.ps1` (contract + unit + integracion
  + migracion 0013 + arquitectura) y registrarlo en `scripts/check.ps1`
- [ ] T049 [P] Escribir los tests de arquitectura que pin `application/
  notifications` como puro (import-linter + AST) en
  `tests/architecture/test_notifications_boundaries.py`
- [ ] T050 [P] Escribir los tests de config de los settings `NOTIFICATIONS_*`
  en `tests/unit/config/test_notifications_settings.py`
- [ ] T051 Documentar la evidencia de aceptacion de H5 en
  `docs/runbooks/evidence/proactive-alerts-acceptance.md` y marcar las 20
  stories UM-H5 en `docs/product/backlog.md`
- [ ] T052 Actualizar `docs/runbooks/configuration.md` con los settings y
  el flujo de notificaciones, y `docs/runbooks/runtime-local.md` con el
  recorrido de alertas

## Dependencies

- **Setup -> Foundational -> US1/US2**: T001..T011 bloquean todas las
  historias (contratos, parser, migracion, repos).
- **US1 -> US2**: el planner consume preferencias versionadas (T014/T016).
- **US2 -> US3**: el duty de plan y el digest usan el planner (T021) y las
  decisiones persistidas (T022).
- **US3 -> US5**: el template de baja (T042) depende del adapter email
  (T027).
- **US4/US5 -> US6**: los eventos viewed/acted/unsubscribed se emiten desde
  inbox y baja (T036/T041) y alimentan el E2E (T047).
- **Polish** cierra el harness sobre todo lo anterior.

## Parallel Execution Examples

- T001..T004 (contratos/settings) pueden ejecutarse en paralelo; T008/T009
  dependen de sus contratos y T010/T011 de nada de US.
- Tras Foundational: US1 (T012..T018) y US2 (T019..T023) pueden avanzar en
  paralelo (planner puro vs API/web de preferencias), con T019..T021
  bloqueados por el golden (T002/T009).
- Dentro de US3: T027..T030 son secuenciales (adapter -> duties -> job);
  T031 es paralelizable.
- US4 y US5 son paralelizables entre si tras US1 (comparten el router, se
  integran en el mismo archivo: coordinar para no pisarse).

## Implementation Strategy (MVP first)

- MVP 1 (US1 + US2): preferencias versionadas + planner puro gated por
  golden — la decision de notificar queda determinista y testeable sin
  entrega real.
- MVP 2 (US3): duties + job de entrega + adapter recording (local) — E2E de
  entrega con fallos simulados.
- MVP 3 (US4 + US5): inbox web + baja — la superficie de producto completa.
- Final (US6 + Polish): instrumentacion, E2E de alertas, harness y cierre.
