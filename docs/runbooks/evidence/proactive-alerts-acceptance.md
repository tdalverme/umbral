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

## Costo de modelo

0 gasto de provider en este incremento (planner deterministico, 0 LLM).
