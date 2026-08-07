# Quickstart: Feedback y aprendizaje controlado (H3.3)

**Feature**: `007-feedback-learning` | **Date**: 2026-08-07

Validation guide for the increment. Full contracts: [feedback](./contracts/feedback-contract-v1.md),
[learning policy](./contracts/learning-policy-v1.md),
[events addendum](./contracts/events-addendum-v1.md); schema in
[data-model.md](./data-model.md).

## Prerequisites

- Local stack up (Postgres/PostGIS/pgvector, Redis) per
  `docs/runbooks/runtime-local.md`; `.venv` activated.
- `006-scoring-explanations` merged (runs v1, evaluations, shortlist) and
  `005-criteria-observations` (facts, compilations).
- `.venv\Scripts\specify.exe check` and `.\scripts\check.ps1` pass before
  starting.

## Scenario 1 — Contratos y reglas puras (FR-001..FR-006, FR-009)

```powershell
uv run pytest tests/contract/test_quick_reasons.py tests/contract/test_learning_policy.py tests/unit/application/feedback
```

Expected: the quick-reasons seed validates keys/polarity/allowed_on; the
learning policy seed validates and versions; invalid seeds and unknown reason
keys are rejected with typed errors; signals aggregate deterministically over
event chains (min_signals/window/cooldown).

## Scenario 2 — Feedback inmutable e idempotente (FR-001..FR-005, SC-001/SC-002)

```powershell
uv run pytest tests/unit/application/feedback/test_feedback_state.py tests/integration/feedback/test_feedback_events.py
```

Expected (integration against real Postgres): every action persists an
immutable event with actor/context/timestamp; replaying the same idempotency
key does not duplicate; a like -> dislike -> like sequence produces three
events with compensation links and the state equals the last event; contacted
is terminal (`feedback_terminal`).

## Scenario 3 — Shortlist y descartados (FR-007/FR-008, SC-004)

```powershell
uv run pytest tests/integration/feedback/test_decision_items.py tests/contract/test_feedback_endpoints.py
```

Expected: save persists the shared `comparison_shortlists` row; un-save
removes it; the decision-items endpoint filters by state and survives reload;
dismissed items are hidden from the radar default view
(`include_dismissed=false`) and visible on demand; 0 runs are created by
direct feedback; cross-search access is denied.

## Scenario 4 — Propuestas de aprendizaje (FR-009..FR-011, SC-005)

```powershell
uv run pytest tests/contract/test_learning_policy.py tests/unit/application/feedback/test_signals.py
```

Expected: 3 consistent reasoned dislikes on `precio` within the window create
one pending proposal with evidence refs; 2 do not; save/dismiss/contacted
never propose; a second proposal on the same concept inside the cooldown is
not created; contradictory evidence supersedes the pending proposal.

## Scenario 5 — Confirmar, deshacer, ampliar y recalcular (FR-012..FR-015, SC-006/SC-007)

```powershell
uv run pytest tests/integration/feedback/test_proposal_lifecycle.py
```

Expected (real Postgres): confirm records the fact
(`fact_source="learning.proposal"`), bumps the profile version, compiles and
submits a run with trigger `edited`; the previous run stays consultable;
undo records a compensating fact and a new run; expand edits the pending
change and shows the diff; confirming an expired/superseded proposal is
rejected (`proposal_expired`/`proposal_not_pending`); a failed run keeps the
last valid one published.

## Scenario 6 — Web: acciones, banner y vistas (FR-005/FR-013, FR-020, SC-003/SC-010)

```powershell
npm run build --workspace @umbral/web
uv run pytest tests/contract/test_web_feedback_slices.py   # contract-level smoke
```

Manual (local API + `npm run dev`): card/detail offer save/dismiss/like/
dislike with reasons, optimistic states revert on failure and undo works
(except contacted); a pending proposal shows the inline radar banner with
confirm/expand/dismiss; shortlist and dismissed views persist per search with
filters; keyboard + screen-reader accessible by convention.

## Scenario 7 — P1: feedback libre e historial de precio (FR-016/FR-017, SC-009)

```powershell
npm run build --workspace @umbral/web
```

Manual with `feedback.free_feedback_enabled=true`: optional free text on
like/dislike explains its use, never reaches analytics; detail shows the price/
attribute history with dates and sources from `known_changes` and declares
"historial insuficiente" without trend lines when the sample is small.

## Scenario 8 — Eventos y harness completo

```powershell
uv run pytest tests/contract/test_events_registry.py
.\scripts\check-feedback.ps1
.\scripts\check.ps1
```

Expected: the nine additive event types pass the closed-registry conformance;
0 payload contains free-feedback text; the feedback harness surface runs
every FR fixture and success metric and is registered in `check.ps1`.

## Out of scope (do not test here)

Golden dataset/regressions (H3.4), chat (H4), alerts (H5), operator console
(H6), global memory across radars (R4-003), criterion-kind proposals (R-06),
embeddings.
