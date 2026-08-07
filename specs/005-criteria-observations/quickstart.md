# Quickstart: Criteria and Observations Validation

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Runnable validation scenarios that prove the H3.1 increment works end-to-end.
Contracts and schema details live in
[contracts/concept-registry-v1.md](./contracts/concept-registry-v1.md),
[contracts/extraction-v1.md](./contracts/extraction-v1.md),
[contracts/compilation-v1.md](./contracts/compilation-v1.md),
[contracts/observations-v1.md](./contracts/observations-v1.md),
[contracts/events-addendum-v1.md](./contracts/events-addendum-v1.md) and
[data-model.md](./data-model.md); this file only drives the validation.

## Prerequisites

- Local Postgres with PostGIS + pgvector (foundation `check-storage.ps1`);
  Redis and object storage (filesystem adapter is enough locally).
- Silver normalization and the search radar from `003`/`004` deployed
  (migration heads `0005`), so `silver_listings` with `description_text`,
  `location_text`, `amenities`, `normalizer_version` and `snapshot_id` exist,
  and `search_profiles`/`search_profile_versions` exist.
- Python env per AGENTS.md (`.venv\Scripts\Activate.ps1`). No web work in this
  increment (FR-024): no npm, no OpenAPI changes, no policy changes.
- The qualitative extraction runs with the fake adapter locally; the managed
  provider adapter is selected by `extraction.provider` in
  preview/production (ADR; Q3 clarification).

## Setup

```powershell
uv sync --frozen --all-groups
uv run alembic upgrade head          # applies 0006_criteria_observations
```

Fixtures live at `tests/fixtures/criteria/`: concepts seed + matcher types
golden, extraction rule golden cases (balcon, ambientes, piso, tipo_cocina),
profile facts golden, compilation golden (incl. soft->hard without
confirmation), observation lineage cases and a reference silver batch reused
from H2.2.

## Scenario 1 — Registry: curaduria y versionado

```powershell
uv run pytest tests/contract/test_concept_registry.py tests/unit/application/criteria/test_registry.py
```

**Expected**: registering the seed v1 produces `concepts` + `concept_versions`
v1 and the `criteria.concept_version_created.v1` event; an edit creates
version 2 without mutating v1 (FR-001); unsupported matcher types or params
are rejected without partial persistence (FR-002); alias collisions warn and
never stay ambiguous (FR-003) (SC-001).

## Scenario 2 — Facts y compilacion de criterios

```powershell
uv run pytest tests/unit/application/criteria/test_facts.py tests/unit/application/criteria/test_compile.py
```

**Expected**: a fact persists value/weight/polarity/confidence/source/validity
per profile; a decision change inserts a new fact and supersedes the previous
without mutation (FR-004); facts are deny-by-default to other users (FR-005).
`compile_criteria` produces the ordered, versioned criterion set with
warnings (FR-006/FR-007/FR-008); a soft preference implying a hard filter
fails or warns without a recorded confirmation and never converts silently;
semantic memory is never compiled without an explicit validated edit (SC-005).

## Scenario 3 — Extraccion objetiva por reglas

```powershell
uv run pytest tests/contract/test_extraction_rules.py tests/unit/application/criteria/test_rules.py
```

**Expected**: every golden case (balcon, ambientes, piso, tipo_cocina)
produces the expected value with the expected fragment evidence (FR-010);
running the same rule twice over the same listing yields identical
observations (SC-004); a listing without a matchable signal produces an
explicit "sin evidencia" observation, never an invented one (SC-002).

## Scenario 4 — Extraccion cualitativa versionada (fake adapter)

```powershell
uv run pytest tests/unit/application/criteria/test_extractor.py tests/contract/test_extraction_versions.py
```

**Expected**: the extractor sends only the permitted projection (FR-014);
valid outputs persist as `active` observations referencing the exact
`extraction_versions` row (FR-013); invalid outputs are rejected or retried
with the bounded budget and final failures persist as `failed` with
`failure_code`, queryable (FR-012); the model never decides ranking (FR-011)
(SC-003).

## Scenario 5 — Recomputacion selectiva y lineage (real DB)

```powershell
uv run pytest tests/integration/criteria/test_recompute.py tests/integration/criteria/test_lineage.py
```

**Expected**: registering a new concept version or extraction version
invalidates automatically only the affected observations
(`active -> invalidated`), leaving the others intact (FR-015); the
`extraction.recompute` job with scope + cause recomputes only the affected
set, publishes new `active` rows and supersedes the invalidated ones in one
transaction, recording `recomputation_runs` with state/counts/cause/times
(FR-016, SC-009); invalidated observations are never used in new results
(FR-017); a failed job leaves no partial observations and no lost versions
(SC-004); the lineage walk observation -> extraction version -> silver
listing -> Bronze snapshot succeeds for 100% of observations (SC-006);
at most one active observation per (listing, concept, source) (SC-012).

## Scenario 6 — Eventos de auditoria versionados

```powershell
uv run pytest tests/contract/test_events_registry.py tests/integration/criteria/test_product_events.py
```

**Expected**: the four new event types validate against the closed registry
and are written in the same transaction as their domain change; payloads carry
only ids/versions/counts; forbidden keys (`value`, `fragment`,
`description_text`, `location_text`, `geometry`, ...) are rejected (SC-010).

## Scenario 7 — P1: embeddings y contexto urbano

```powershell
uv run pytest tests/integration/criteria/test_embeddings.py tests/integration/criteria/test_urban_signals.py
```

**Expected** (P1, after the first internal pass): embeddings are generated
only from the permitted projection with model version registered; 0 embeddings
from raw HTML or PII (FR-018, SC-007); a model/text change regenerates only
affected embeddings preserving previous versions (FR-019). Urban signals carry
source, date, geometry and algorithm for 100% of rows and respect the
authorized `geo_precision` (FR-020, SC-008); external queries are cached and
rate-limited (FR-021).

## Full gate

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic check
uv run alembic current --check-heads
.\scripts\check.ps1          # includes scripts/check-criteria.ps1
```

No success claim is based only on mocks: scenarios 5, 6 and 7 run against the
real Postgres/PostGIS/pgvector stack via testcontainers, following
`tests/integration/criteria` conventions; the qualitative extraction uses the
fake adapter locally and the managed adapter is exercised in preview/
production with the same contract conformance.
