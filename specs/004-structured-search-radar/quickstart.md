# Quickstart: Structured Search Radar Validation

**Feature**: `004-structured-search-radar` | **Date**: 2026-08-06

Runnable validation scenarios that prove the H2.3 increment works end-to-end.
Contracts and schema details live in
[contracts/search-profile-v1.md](./contracts/search-profile-v1.md),
[contracts/scoring-baseline-v1.md](./contracts/scoring-baseline-v1.md),
[contracts/events-v1.md](./contracts/events-v1.md) and
[data-model.md](./data-model.md); this file only drives the validation.

## Prerequisites

- Local Postgres with PostGIS + pgvector (foundation `check-storage.ps1`),
  Redis and object storage (filesystem adapter is enough locally).
- Silver normalization from `003-silver-normalization` deployed (migration
  heads `0004`), so `silver_listings` with declared `geo_precision` exist.
- Identity from H1.3 (invitations/magic link) or the harness test actor, so a
  session cookie yields a `product_user` with role `user`.
- Python env per AGENTS.md (`.venv\Scripts\Activate.ps1`); Node >= 24 for
  `apps/web`.

## Setup

```powershell
uv sync --frozen --all-groups
uv run alembic upgrade head          # applies 0005_search_radar
npm run api:generate --workspace @umbral/web   # regenerates the typed client
npm run dev --workspace @umbral/web
```

The radar fixture lives at `tests/fixtures/radar/`: a reference silver batch
(reused from H2.2) plus golden search profiles covering hard filters with
unknown values, budget bounds, zones without geometry and profile edits.

## Scenario 1 — Crear radar y ver estado de generacion

```powershell
uv run pytest tests/integration/radar/test_run_pipeline.py
```

**Expected**: creating a profile (POST via the API or the service) persists the
profile + version 1 and submits the `recommendation.run` job; the run reaches
`succeeded` in under 30 s over the fixture; the radar shows "generando
resultados" while pending/running and the published items after (FR-023,
SC-011, SC-013). A failed run (induced) keeps the last succeeded run as the
only visible result (FR-013, SC-004).

## Scenario 2 — Hard filters golden (incl. unknown policy)

```powershell
uv run pytest tests/contract/test_search_profile_contract.py tests/unit/application/radar/test_hard_filters.py
```

**Expected**: every golden case produces the declared outcome: price unknown ->
excluded; zone unknown/outside -> excluded; rooms/surface unknown -> included
with the declared scoring fit; budget bounds and zone lists applied exactly
(FR-009, FR-010, SC-002).

## Scenario 3 — Determinismo del scoring y desglose

```powershell
uv run pytest tests/contract/test_scoring_baseline.py tests/unit/application/radar/test_scoring.py
```

**Expected**: running the same profile twice over the same candidate set
produces identical order, scores and `contributions` JSONB (SC-003); the
breakdown is exposed in the match detail and never in cards (FR-012, SC-012);
tie-break `(score desc, total_cost asc, listing_id asc)` is stable.

## Scenario 4 — Paginacion estable del radar

```powershell
uv run pytest tests/integration/radar/test_matches_pagination.py
```

**Expected**: paging the matches of one `run_id` yields 0 repeated and 0
omitted items across pages; a new run changes the visible set only when the
client switches `run_id` (SC-003).

## Scenario 5 — Edicion concurrente y transiciones

```powershell
uv run pytest tests/integration/radar/test_profile_editing.py
```

**Expected**: PATCH with a stale `expected_version` returns the typed
concurrency error and loses nothing silently (FR-006); editing an active
profile creates version 2, marks results obsolete and triggers a new run while
the previous run and items stay queryable (FR-015, SC-001); pause stops new
runs, resume re-runs, archive hides but preserves (FR-003, US2).

## Scenario 6 — Eventos de producto versionados

```powershell
uv run pytest tests/contract/test_events_registry.py tests/integration/radar/test_product_events.py
```

**Expected**: `radar.created.v1` and `recommendation.run_published.v1` rows
exist after the Scenario 1 flow; client events (impression, detail_viewed,
source_opened) are accepted only with valid registry payloads and rejected
(400) with unknown types or PII keys; events referencing another user's
profile are rejected (403) (FR-020, SC-007).

## Scenario 7 — Prevision del recorrido E2E web

```powershell
npm run test:e2e --workspace @umbral/web   # tests/e2e/radar.spec.ts
```

**Expected**: with the harness test actor, a user completes onboarding (3
steps + resumen + confirmacion), sees the radar cards/lista with score total,
opens a match detail with the breakdown, opens the map with precision-respecting
points, and every state (loading, empty, error, no autorizado, no encontrado)
is distinguishable in desktop and mobile (FR-019, FR-022, SC-006, SC-009,
SC-010). Map points never exceed the authorized `geo_precision` (SC-005).

## Scenario 8 — Recorrido E2E idempotente

```powershell
uv run pytest tests/integration/radar/test_e2e_reimport.py
```

**Expected**: importing the fixture batch (H2.1) and walking
lote -> reporte -> Silver -> radar -> detalle yields correct results; a second
import of the same batch produces 0 duplicate listings, 0 duplicate runs and 0
duplicate matches (FR-021, SC-008).

## Full gate

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic check
uv run alembic current --check-heads
.\scripts\check.ps1          # includes scripts/check-radar.ps1 and check-web.ps1
```

No success claim is based only on mocks: scenarios 1, 4, 5, 6 and 8 run
against the real Postgres/PostGIS stack via testcontainers, following
`tests/integration/radar` conventions; scenario 7 runs against the web app
with the e2e mock identity.
