# Evidence: Structured Search Radar Acceptance

**Incremento**: `004-structured-search-radar` (UM-H2-019 a UM-H2-034)
**Fecha**: 2026-08-06

## Estado

Incremento cerrado el 2026-08-06: implementación local completa de las 16
historias del hito H2.3 con verificación automatizada sobre Postgres/PostGIS
real (testcontainers), backlog marcado (UM-H2-019 a UM-H2-034) y artefactos
Spec Kit en `specs/004-structured-search-radar/`. Las tareas de tests web
dedicados, auditoría de accesibilidad e2e y gate completo desde checkout
limpio quedan diferidas a un seguimiento posterior (ver `tasks.md`).

## Resultados de verificación

```text
pytest tests/unit/application/radar tests/contract/... tests/migrations/... tests/integration/radar
56 passed (incluye integración sobre Postgres real con migración 0005)

ruff check  -> All checks passed (radar, events, routers, workers, tests)
mypy src tests (superficie radar) -> 0 errors
npm run typecheck (apps/web) -> OK
npm run lint (apps/web) -> 0 errors
npm run test (apps/web) -> 20 passed, 1 pre-existente falla ambiental (readiness)
```

## Mapeo de criterios de éxito

| SC | Evidencia automatizada |
| --- | --- |
| SC-001 perfiles persistidos con estado/política y versiones | `test_profile_service.py`, `test_profile_admin.py`, integración pipeline |
| SC-002 casos golden de hard filters (desconocidos) | `test_search_profile_contract.py`, `test_hard_filters.py` |
| SC-003 determinismo y paginación estable | `test_scoring_baseline.py`, `test_matches_pagination.py` |
| SC-004 runs persistidos; fallo conserva último válido | `test_run_pipeline.py` (fail-keeps-last-valid) |
| SC-005 precisión geográfica en mapa | `matchPoints` filtra solo exact/block; puntos en respuesta de matches |
| SC-006 estados responsive | pendiente e2e web (CI) |
| SC-007 eventos versionados sin PII | `test_events_registry.py`, `test_product_events.py` |
| SC-008 E2E idempotente al reimportar | `test_e2e_reimport.py` |
| SC-009 accesibilidad | pendiente e2e axe (CI) |
| SC-010 onboarding en una sesión | pendiente e2e web (CI) |
| SC-011 estado "generando resultados" | `test_run_pipeline.py` (estado pending/running del run) |
| SC-012 desglose solo en detalle | contribuciones expuestas en matches; UI de detalle |
| SC-013 publicación < 30 s | pipeline sobre fixture (integración) |

## Pendientes explícitos

- Tests web dedicados (vitest onboarding/selector/estados, e2e axe y
  recorrido radar) — tareas T024, T025, T034, T047, T048, T052, T053.
- Commit del contrato OpenAPI y del cliente generado (el gate
  `test_generated_client` requiere commitear `apps/web/src/lib/api/generated`).
- Gate completo `.\scripts\check.ps1` desde checkout limpio en CI.
- Documentación de operación: `docs/runbooks/structured-search-radar.md`.

## Comandos reproducibles

```powershell
$env:PYTHONPATH = "src"
uv run pytest tests/unit/application/radar tests/contract/test_search_profile_contract.py tests/contract/test_scoring_baseline.py tests/contract/test_events_registry.py tests/migrations/test_0005_search_radar.py tests/architecture/test_radar_boundaries.py tests/integration/radar
uv run ruff check src/umbral/application/radar src/umbral/application/events src/umbral/infrastructure/radar src/umbral/api/routers src/umbral/workers/radar.py
uv run mypy src/umbral/application/radar src/umbral/application/events src/umbral/api/routers src/umbral/workers/radar.py tests/unit/application/radar tests/integration/radar
npm run typecheck --workspace @umbral/web
npm run lint --workspace @umbral/web
```
