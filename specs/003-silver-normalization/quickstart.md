# Quickstart: Silver Normalization Validation

**Feature**: `003-silver-normalization` | **Date**: 2026-08-06

Runnable validation scenarios that prove the H2.2 increment works end-to-end.
Contracts and schema details live in
[contracts/silver-schema-v1.md](./contracts/silver-schema-v1.md),
[contracts/dedupe-policy-v1.md](./contracts/dedupe-policy-v1.md) and
[data-model.md](./data-model.md); this file only drives the validation.

## Prerequisites

- Local Postgres with PostGIS + pgvector (foundation `check-storage.ps1`),
  Redis and object storage (filesystem adapter is enough locally).
- Bronze ingestion from `002-bronze-ingestion` deployed (migration heads
  `0003`), so importing a batch produces `raw_listing_snapshots`.
- Python environment per AGENTS.md (`.venv\Scripts\Activate.ps1`).

## Setup

```powershell
uv sync --frozen --all-groups
uv run alembic upgrade head          # applies 0004_silver_normalization
```

The reference fixture lives at `tests/fixtures/silver/reference-batch.json`:
listings validos, duplicados exactos (misma fuente) y entre fuentes, duplicados
ambiguos, cambios de precio, campos faltantes, ubicaciones aproximadas y casos
que van a cuarentena (cumple UM-H0-010).

## Scenario 1 — Import y normalizacion de punta a punta

```powershell
uv run pytest tests/integration/silver/test_normalization_pipeline.py
```

**Expected**: after importing `reference-batch.json` (operator entry of H2.1),
the chained `ingestion.normalize_batch` job runs; every valid snapshot produces
one `silver_listings` row with source identity, url, published_at,
last_observed_at, snapshot reference and `normalizer_version=silver-schema-v1`;
quarantined records produce no silver rows. SC-001.

## Scenario 2 — Precio, atributos y ubicacion sin inventar

```powershell
uv run pytest tests/contract/test_silver_schema.py tests/unit/application/silver/
```

**Expected**: 100% of prices preserve original currency/value; a missing rate
records `price_assumptions`, zero conversions (SC-003). Out-of-range attributes
produce `normalization_errors` codes, never guessed values (SC-002). Location
precision follows silver-schema-v1; zero listings with invented addresses or
coordinates (SC-006).

## Scenario 3 — Canonical properties y dedupe

```powershell
uv run pytest tests/unit/application/silver/test_dedupe.py tests/integration/silver/test_dedupe_golden.py
```

**Expected**: exact same-source duplicates share one canonical (chain);
deterministic cross-source pairs (all strong fields present and equal) are
linked `confirmed` with fingerprint + evidence and share one canonical; ambiguous
pairs are `pending` proposals with score + evidence, zero auto-merges (SC-004).

## Scenario 4 — Cambios entre versiones

```powershell
uv run pytest tests/integration/silver/test_changes.py
```

**Expected**: a second publication changing price emits a `listing_changes` row
(change_type `price`) with before/after/origin; text/attribute changes likewise;
an identical re-publication emits zero changes (SC-005).

## Scenario 5 — Lineage Bronze-Silver

```powershell
uv run pytest tests/integration/silver/test_lineage.py
```

**Expected**: for every reference entity, walking
`silver_listings.snapshot_id` → `raw_listing_snapshots` → `import_runs` yields
the snapshot and parser version that produced it; `normalizer_version` is
present on every row (SC-007).

## Scenario 6 — Reproceso idempotente

```powershell
uv run pytest tests/integration/silver/test_reprocess_idempotency.py
```

**Expected**: re-running the normalization job for the same run produces zero
new silver rows, zero false changes and zero duplicate links; a new
`normalizer_version` creates new rows while the previous ones remain unchanged
(SC-008).

## Scenario 7 — Geocodificacion (P1)

```powershell
uv run pytest tests/integration/silver/test_silver_geocoding.py
```

**Expected**: geocodable locations resolve through the registered adapter with
cache and rate limits (zero requests beyond configured bounds); precision never
improves beyond input granularity; failures degrade to `unknown` without
blocking the batch (SC-006).

## Full gate

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic check
uv run alembic current --check-heads
.\scripts\check.ps1          # includes scripts/check-silver.ps1
```

No success claim is based only on mocks: scenarios 1, 4, 5, 6 and 7 run against
the real Postgres/object-storage stack via testcontainers, following
`tests/integration/silver` conventions.
