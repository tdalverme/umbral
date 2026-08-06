# Runbook: Structured Search Radar (H2.3)

**Incremento**: `004-structured-search-radar` | **Fecha**: 2026-08-06

## Qué opera este incremento

- Radars (search profiles) por usuario: crear, listar, editar (concurrencia
  por `expected_version`), pausar, reanudar y archivar. Transiciones v1:
  activo <-> pausado; activo/pausado -> archivado (archivado terminal).
- Runs asincrónicos (`recommendation.run`): al crear/editar un radar activo se
  dispara un job durable que aplica hard filters (presupuesto, zonas,
  ambientes; desconocidos según la política versionada del perfil), calcula el
  scoring baseline determinista y publica `recommendation_items` atómicamente.
  Un run fallido conserva el último run válido como único resultado visible.
- Radar en lista/cards y mapa (MapLibre con tiles OSM públicos): los puntos se
  renderizan solo con precisión `exact`/`block`; el resto aparece solo en la
  lista. El desglose del score aparece únicamente en el detalle del match.
- Eventos de producto versionados (`contracts/events/v1`): `radar.created.v1`
  y `recommendation.run_published.v1` los emite el servidor; `impression`,
  `detail_viewed` y `source_opened` los emite el cliente vía
  `POST /api/v1/product-events` (validación cerrada, sin PII).

## Comandos de operación

```powershell
# Migración
uv run alembic upgrade head

# API de desarrollo
uvicorn umbral.api.main:app --reload

# Workers (incluye el handler recommendation.run)
python -m umbral.workers worker

# Harness del incremento
.\scripts\check-radar.ps1
.\scripts\check.ps1
```

## Contratos vigentes

- `contracts/search-profiles/v1/search-profile-policy.json` — validación,
  barrios CABA, estrategias de desconocidos y transiciones.
- `contracts/scoring/v1/scoring-baseline.json` — pesos, funciones de fit y
  tie-break del scoring baseline v1.
- `contracts/events/v1/events-registry.json` — registry cerrado de eventos.
- `contracts/openapi/v1/openapi.json` — contrato HTTP (mayor 1, aditivo).

## Estados visibles del radar

- `pending`/`running`: el radar muestra "Generando resultados…" (polling 3 s).
- `succeeded`: lista de matches del run congelado (paginación estable por
  `run_id` + `position`).
- `failed`: se conserva el último run válido; el error queda en `failure_code`.
- Sin resultados: estado vacío con siguiente paso sugerido.

## Verificación manual rápida (local)

1. Levantar API + workers con Postgres local en head (`0005`).
2. Importar un lote (H2.1) y verificar Silver (H2.2).
3. Crear un radar desde `POST /api/v1/search-profiles` con sesión de usuario.
4. Esperar el run y listar `GET /api/v1/search-profiles/{id}/matches`.
5. Abrir el detalle `GET /api/v1/listings/{listing_id}` (autorizado por runs).
6. Verificar eventos en la tabla `product_events`.

## Recorrido local de punta a punta (Windows)

Levanta el stack completo contra Postgres/Redis locales con el runtime durable
real (outbox → scheduler → worker):

```powershell
# 1. Servicios (Docker)
docker run -d --name umbral-pg -e POSTGRES_USER=umbral -e POSTGRES_PASSWORD=local -e POSTGRES_DB=umbral -p 5432:5432 ghcr.io/pglayers/pglayers-full:17
docker run -d --name umbral-redis -p 6379:6379 redis:8.6.4-alpine

# 2. Migraciones
$env:DATABASE_URL = "postgresql://umbral:local@127.0.0.1/umbral"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m alembic upgrade head

# 3. Seed: usuario demo + sesión + 6 listings Silver (imprime la cookie)
.\.venv\Scripts\python.exe scripts\seed-local.py

# 4. Procesos (sin variables de entorno para worker/scheduler: usan defaults locales)
$env:UMBRAL_ENV = "local"; $env:UMBRAL_RELEASE_ID = "foundation-local"; $env:UMBRAL_RELEASE_MANIFEST = "<local>"
$env:DATABASE_URL = "postgresql://umbral:local@127.0.0.1/umbral"; $env:REDIS_URL = "redis://127.0.0.1:6379/0"
$env:OBJECT_STORE_BACKEND = "filesystem"; $env:OBJECT_STORE_ROOT = ".umbral-local"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4318"; $env:UMBRAL_API_BASE_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m uvicorn umbral.api.dev_main:app --port 8000   # API durable + identidad SQLAlchemy
.\.venv\Scripts\python.exe -m umbral.workers worker                            # RQ SimpleWorker en Windows
.\.venv\Scripts\python.exe -m umbral.workers scheduler                         # relay outbox -> Redis

# 5. Web
$env:UMBRAL_ACCESS_MODE = "product_session"; $env:SESSION_COOKIE_NAME = "umbral_local_session"
$env:UMBRAL_E2E_BYPASS_ACCESS = "1"; $env:UMBRAL_BFF_TOKEN = "local-bff-token"
$env:UMBRAL_API_BASE_URL = "http://127.0.0.1:8000"; $env:UMBRAL_PRIVATE_API_URL = "http://127.0.0.1:8000"
npm run dev --workspace @umbral/web
```

Notas:

- La API local de dev usa `umbral.api.dev_main:app`: runtime durable real
  (Postgres + Redis) e identidad SQLAlchemy, con adapters de proveedor dummy
  (Supabase/Resend nunca se llaman). El magic link no aplica: la sesión se
  siembra con `scripts/seed-local.py`, que imprime el valor de la cookie
  `umbral_local_session` para pegar en DevTools (Application -> Cookies) del
  navegador sobre `http://localhost:3000`.
- El worker elige `SimpleWorker` en Windows (RQ no puede hacer fork); en
  Linux/CI sigue usando el worker estándar.
- `/ready` de la API puede reportar 503 (probes de preview sin MinIO/collector)
  sin afectar la operación; `/health` responde 200.
- Para detener: `docker stop umbral-pg umbral-redis` y finalizar los procesos
  python de uvicorn/worker/scheduler y el `next dev`.

## Notas operativas

- Los tiles OSM públicos requieren atribución; si el tile server falla, el
  mapa muestra error recuperable y la lista sigue operativa. Proveedor
  comercial y CSP de tiles: revisión en H6-013.
- Los runs corren sobre el dataset controlado de beta; objetivo de publicación
  < 30 s (SC-013). No hay rate limits de producto en este incremento.
- El operador no tiene superficie sobre radares de usuarios; la verificación
  E2E usa el actor de prueba del harness.
