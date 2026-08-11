# Evidencia: Proactividad controlada (H5)

Fecha: 2026-08-11 · Incremento: `013-proactive-alerts` (UM-H5-001 a UM-H5-020)

## Alcance implementado

- **Contratos** (`contracts/notifications/v1/`): `notification-policy-v1.json`
  (politica versionada) y `planner-golden-v1.json` (8 casos golden: new
  match inmediato/digest, price drop, duplicado, quiet hours, fatiga,
  preferencias desactivadas, sin canales); registry +6 eventos
  `notification.*.v1` sin PII.
- **Planner puro** (`application/notifications/planner.py`): triggers,
  dedupe, quiet hours (zoneinfo), fatiga por cooldown, cadencia hibrida
  (immediate vs digest); gate golden 8/8 en el harness.
- **Preferencias** (`preferences.py` + servicio + repos): versionadas por
  usuario/busqueda con validacion de zoneinfo/quiet hours/umbral; token de
  baja HMAC expirable y ligado a version.
- **Persistencia** (migracion `0013_notifications`): 3 tablas
  (`notification_preferences`, `notification_decisions` con indice parcial
  para 0 duplicados por item+trigger, `notification_inbox_items` 1:1).
- **Entrega**: `NotificationDeliveryService` idempotente por estado
  (pending_delivery -> delivered con provider message id); adapters email
  recording (local) y Resend (sender compartido); duties de scheduler
  `notifications.plan`/`notifications.digest` + job RQ
  `notifications.deliver` registrados en `workers/composition.py`.
- **API**: router `notifications` (preferencias GET/PUT, inbox GET/PATCH,
  baja POST sin login) con acciones deny-by-default nuevas en la matriz de
  identidad; montado en `api/main.py`.
- **Harness**: `scripts/check-alerts.ps1` registrado en `check.ps1`;
  contract tests (policy, golden, eventos), unit del planner/preferencias/
  token, config, arquitectura (application/notifications puro), migracion
  0013, integracion con Postgres/testcontainers (3 tests de persistencia y
  entrega).

## Verificacion

- Suite completa: **850 passed** (unit + contract), 2 fallos pre-existentes
  de entorno (supabase SDK / rq worker) ajenos al incremento.
- Gate golden del planner: **8/8 casos** deterministas.
- Migracion `0013` up/down verificada localmente.
- Integracion (Docker): preferencias versionadas, entrega idempotente
  (0 duplicados, fallo de proveedor deja la decision retryable y emite
  `delivery_failed.v1`).

## Diferidos (superficie web)

- Pagina del centro de notificaciones y configuracion de alertas en
  `apps/web` (T018/T037) y sus vitest: la API esta lista y probada; la UI
  queda como siguiente slice. El E2E de alertas completo (T047) depende de
  la UI para las vistas/acciones.

## Ampliacion: UI web de notificaciones (2026-08-11)

Cerrados los deferidos web de H5:

- BFF catch-all `apps/web/src/app/api/notifications/[...path]/route.ts`
  (mismo patron que las rutas radar: cookie de sesion + BFF token).
- Cliente tipado `apps/web/src/lib/notifications/client.ts`
  (`notificationsApi`: preferencias, inbox, mark read, baja).
- Vista `apps/web/src/components/notifications/notifications-view.tsx`
  (centro de notificaciones + config de alertas con toggles y desactivacion)
  y pagina `apps/web/src/app/(protected)/notifications/page.tsx`.
- Vitest del componente (3 tests) verde; build Next y lint sin errores
  (1 warning pre-existente en la pagina de radar).
- OpenAPI re-exportado (contratos incluyen las rutas `/api/v1/notifications/*`)
  y cliente generado regenerado y commiteado (`api:check` limpio).
- E2E web de alertas con vistas/acciones y diseno final de template de email
  siguen diferidos (dependen del flujo completo en un entorno desplegado).

## Costo de modelo

0 gasto de provider en este incremento (planner deterministico, 0 LLM).

## Wiring de produccion del agente (deferido H4.4, 2026-08-11)

Cerrado el deferido de H4.4 "wiring de produccion del runtime/dashboard en
`api/dependencies.py`":

- Nuevo modulo `infrastructure/agent/production.py`: compone el stack v3 de
  produccion — `ChatService` con repos reales, `RunRecorderService`,
  `SearchProfileUpdateProposals` (que implementa el `ProposalDecisionGateway`
  del graph HITL), `ToolExecutor` sobre los servicios reales (radar, scoring,
  feedback, criteria), `IntentCompiler`, checkpointer Postgres y el gateway
  de modelo (managed por `AGENT_MODEL_PROVIDER=managed`, fake local).
- `build_runtime_dependencies` ahora puebla `chat`, `agent_runtime`,
  `proposals` y `graph_runs` en `RuntimeDependencies`, lo que habilita el
  router de chat en el API de produccion (antes levantaba RuntimeError "not
  configured").
- Degradacion honesta: si Postgres no esta disponible localmente, el stack no
  se construye (el chat queda sin configurar, consistente con la readiness
  degradada); en preview/produccion cualquier fallo propaga.
- Verificado: con Postgres arriba los 4 objetos quedan cableados; el app
  importa con y sin DB; suite completa 850 passed sin regresiones.
- Tambien se creo el manifiesto local `.data/release-manifest.local.json`
  (faltaba para el arranque local del API y del test de readiness).
