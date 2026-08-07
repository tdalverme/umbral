# Quickstart: Scoring and Explanations (H3.2)

**Feature**: `006-scoring-explanations` | **Date**: 2026-08-07

Validation guide for the increment. Full contracts: [scoring policy](./contracts/scoring-policy-v1.md),
[explanations](./contracts/explanations-v1.md), [comparison](./contracts/comparison-v1.md),
[events addendum](./contracts/events-addendum-v1.md); schema in
[data-model.md](./data-model.md).

## Prerequisites

- Local stack up (Postgres/PostGIS/pgvector, Redis) per
  `docs/runbooks/runtime-local.md`; `.venv` activated.
- Baseline from `005-criteria-observations` merged (concepts, observations,
  compilations) and `004-structured-search-radar` (runs).
- `.venv\Scripts\specify.exe check` and `.\scripts\check.ps1` pass before
  starting.

## Scenario 1 — Policy v1 versionado y validado (FR-001/FR-002)

```powershell
uv run pytest tests/contract/test_scoring_policy.py tests/unit/application/scoring
```

Expected: registering/editing a policy creates immutable versions; a policy
with non-normalizing weights, unknown matcher type, invalid params or unknown
gate is rejected without persisting partial data; the seed
`scoring-policy-v1` loads from `contracts/scoring/v1/scoring-policy-v1.json`.

## Scenario 2 — Evaluadores golden y determinismo (FR-004..FR-008, SC-001/SC-003)

```powershell
uv run pytest tests/contract/test_evaluators.py tests/unit/application/scoring/test_engine.py
```

Expected: golden fixtures per matcher type produce the expected
score/confidence/state/evidence; unknown never counts as mismatch; running
`score_candidates` twice over the same inputs yields identical order and
breakdown with no I/O.

## Scenario 3 — Run v1 publica evaluaciones atómicamente (FR-010/FR-011, SC-005/SC-006)

```powershell
uv run pytest tests/integration/scoring/test_run_v1.py
```

Expected (against real Postgres): a run with the v1 policy publishes
`recommendation_items` + `criterion_evaluations` + `run_published.v1` in one
transaction; an induced mid-run failure keeps the last valid run visible with
cause recorded and no partial evaluations; a later observation recompute does
not invalidate the published run.

## Scenario 4 — Explicaciones deterministas por listing y por búsqueda (FR-012..FR-015, SC-007/SC-008)

```powershell
uv run pytest tests/contract/test_explanations.py tests/contract/test_explanation_endpoints.py
```

Expected: `build_explanation` returns reasons with evidence refs, risks,
missing data and confidence from the frozen run; two calls produce identical
copy; a legacy run (`scoring-baseline-v1`) returns
`explanation_unavailable`; cross-user/cross-run access is denied with typed
problems.

## Scenario 5 — Comparación estructurada (FR-016/FR-017, SC-009)

```powershell
uv run pytest tests/contract/test_comparison.py
```

Expected: 2..limit listings of the same run compare with fixed + criterion
dimensions; missing cells are visible as missing; over-limit, duplicate or
cross-search requests are rejected; no winner is computed.

## Scenario 6 — Web: razones en cards/detalle y comparador P1 (FR-018..FR-020, SC-011/SC-012)

```powershell
npm run build --workspace @umbral/web
uv run pytest tests/contract/test_web_radar_slices.py   # contract-level smoke
```

Manual (local API + `npm run dev`): cards show up to 3 reasons with evidence
levels; detail shows the full breakdown and confidence; a legacy run shows the
score with the "explicación no disponible" notice; with
`scoring.comparator_enabled=true`, the shortlist persists across reload and
the matrix renders responsive (P1).

## Scenario 7 — Eventos y harness completo

```powershell
uv run pytest tests/contract/test_events_registry.py
.\scripts\check-scoring.ps1
.\scripts\check.ps1
```

Expected: the two additive events (`recommendation.explanation_viewed.v1`,
`recommendation.comparison_viewed.v1`) pass the closed-registry conformance;
the scoring harness surface runs every FR fixture and success metric and is
registered in `check.ps1`.

## Out of scope (do not test here)

Feedback (H3.3), golden dataset/regressions (H3.4), chat (H4), alerts (H5),
operator console (H6), embeddings (P1 of H3.1, unused by semantic_feature).
