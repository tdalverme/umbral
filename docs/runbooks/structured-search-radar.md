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

## Notas operativas

- Los tiles OSM públicos requieren atribución; si el tile server falla, el
  mapa muestra error recuperable y la lista sigue operativa. Proveedor
  comercial y CSP de tiles: revisión en H6-013.
- Los runs corren sobre el dataset controlado de beta; objetivo de publicación
  < 30 s (SC-013). No hay rate limits de producto en este incremento.
- El operador no tiene superficie sobre radares de usuarios; la verificación
  E2E usa el actor de prueba del harness.
