# Research: Scoring and Explanations (H3.2)

**Feature**: `006-scoring-explanations` | **Date**: 2026-08-07 | **Spec**:
[spec.md](./spec.md)

Decisions and rejected alternatives for UM-H3-012 through UM-H3-022. Each item
records Decision, Rationale, and Alternatives considered, grounded in the
existing codebase (radar H2.3, criteria H3.1).

## R-01 — Scoring v1 replaces the baseline inside the existing run job

**Decision**: The `recommendation.run` job keeps its current lifecycle
(profile version frozen, candidate set computed once, atomic publish via
`record_outcome`). The scoring engine inside it switches from
`application/radar/scoring.py` (baseline) to the policy v1 engine. The run row
already carries `score_policy_version`; runs keep whatever version string they
were produced with.

**Rationale**: The spec assumption says v1 "evoluciona la maquinaria de runs de
H2.3" and replaces the baseline. Keeping the job identity, idempotency and
atomic publish unchanged minimizes risk and preserves the `< 30 s` publish
target; legacy runs remain visible untouched (clarification 2026-08-07).

**Alternatives considered**: (a) a second engine coexisting behind a setting —
rejected, it would double the run paths for no beta need; (b) a full backfill
of legacy runs — rejected by clarification (no migration/backfill).

## R-02 — Scoring policy persists like the concept registry (append-only versions)

**Decision**: `scoring_policies` + immutable `scoring_policy_versions` mirroring
the `concepts`/`concept_versions` pattern of H3.1. The version payload is a
JSONB document validated against `contracts/scoring/v1/scoring-policy-v1.json`
(weights, normalization, gates, confidence policy, bonuses, penalties,
tie-break, score_round). The curated seed `scoring-policy-v1` is loaded at
startup (setting `scoring.policy_seed_version`), like the concept seed.

**Rationale**: The spec (FR-001/FR-002) requires immutable versioned policies
with validation of weights/gates/references; the registry pattern already
exists, tested and audited.

**Alternatives considered**: (a) plain JSON settings file without persistence —
rejected, runs must reference a persisted, immutable version (FR-003);
(b) structured columns per policy field — rejected, the policy is a document
whose shape evolves with matcher types; JSONB with a versioned contract keeps
validation at the contract boundary.

## R-03 — Four generic evaluators, pure, with one small output contract

**Decision**: Pure evaluators `numeric_range`, `categorical`, `geo_proximity`
and `semantic_feature` in `application/scoring/evaluators.py`, each
implementing the same contract: inputs (criterion params from the compilation,
observations of the listing, listing data), output
`Evaluation(score, confidence, state, reason_code, evidence_refs)`. Params are
validated against the H3.1 `matcher-types-v1.json` `allowed_params`. Golden
fixtures per evaluator type.

**Rationale**: FR-004 requires one common output contract; the matcher types
are already registered by H3.1, so validation is shared. `semantic_feature`
evaluates qualitative observations (luminosidad, estado_general) produced by
H3.1; it does NOT require embeddings (those are P1 and unused here).

**Alternatives considered**: (a) one evaluator per criterion at policy level —
rejected, violates the shared-contract requirement; (b) semantic evaluator
deferred — rejected, the spec lists it among the initial evaluators and it is
feasible on H3.1 observations.

## R-04 — Unknown is a first-class state, not a score

**Decision**: Every evaluation returns `state` in
`{match, mismatch, unknown}`. `unknown` contributes neutrally to the score
(weight applies a neutral baseline or is skipped per policy), lowers the
overall confidence, and is never counted as a mismatch. `match`/`mismatch`
carry the observed evidence. Reason codes and UI copy distinguish the three
states (FR-006, SC-004).

**Rationale**: The spec (UM-H3-014) requires the distinction to be observable
in serialization and UI. A tri-state result keeps evaluators pure and the
policy in control of how unknown affects confidence.

**Alternatives considered**: (a) unknown encoded as score 0.5 with a flag —
rejected, mixes semantics into the score; (b) unknown handled only at policy
level — rejected, evaluators must return it so evidence and confidence are
consistent per evaluation.

## R-05 — Criterion evaluations are persisted per run and immutable

**Decision**: `criterion_evaluations` rows: (run_id, listing_id, criterion_key,
criterion_version, concept_id, matcher_type, params, input_refs (observation
ids + versions used), score, confidence, state, contribution, reason_code,
evidence_refs). Unique on (run_id, listing_id, criterion_key). Because runs are
frozen and append-only, evaluations are written once with the run and never
mutated; they ARE the feature snapshot of the run (FR-007, FR-010).

**Rationale**: FR-007 requires inputs/contribution/reason persisted with
versions; observations in H3.1 are append-only with versions, so referencing
(observation_id, observation_version) reconstructs lineage even after later
recomputes. No separate feature-snapshot table is needed.

**Alternatives considered**: (a) storing evaluation JSON inside
`recommendation_items.contributions` — rejected, breaks queryability,
lineage and per-criterion evidence; (b) a `run_feature_snapshots` table —
rejected as redundant with append-only observations + evaluation input refs.

## R-06 — Scoring is a pure function with deterministic order

**Decision**: `score_candidates(profile_snapshot, compilations, candidates,
observations, policy) -> tuple[ScoredCandidate, ...]` in
`application/scoring/engine.py`, pure (no I/O). Order: score desc, then policy
tie-break keys, then listing_id asc. The same inputs produce the same order,
scores and breakdown (FR-008, SC-001), verified by double-run tests.

**Rationale**: The spec makes determinism a success criterion; keeping the
engine free of I/O makes that provable by test and reuses the existing
tie-break convention of the baseline.

**Alternatives considered**: (a) streaming evaluation interleaved with DB reads
— rejected, couples determinism to data fetching; the run job loads the frozen
inputs first (bounded by the candidate set of the run).

## R-07 — Run publication stays atomic via the existing record_outcome pattern

**Decision**: The handler publishes run + items + criterion_evaluations +
`recommendation.run_published.v1` in one transaction (the H2.3
`record_outcome` pattern). A failed run keeps the last valid run visible and
records `failure_code` (FR-011). Runs never invalidate when observations or
Silver change (clarification 2026-08-07; FR-010).

**Rationale**: Atomicity and failure behavior already exist and are tested in
H2.3; evaluations extend the same transaction. The clarification removes any
invalidation state machine from this increment.

**Alternatives considered**: (a) publishing evaluations in a second transaction
— rejected, partial evaluation sets would break lineage; (b) an
invalidated/regenerate state on runs — rejected by the clarification (that is
H3.3 UM-H3-030).

## R-08 — Explanations are generated on demand, deterministically, from evaluations

**Decision**: `build_explanation(run, evaluations, policy, copy_templates) ->
Explanation` in `application/scoring/explanations.py`, pure. Output: reasons
(criterion, contribution, evidence refs, evidence level strong/medium/low),
risks (low-confidence evaluations and missing data with policy-defined
thresholds), missing data list, global confidence, score version, profile and
feature snapshot references. Copy is template-based (clarification 2026-08-07);
templates live in `contracts/scoring/v1/explanations-v1.json`. No LLM, no new
table. Legacy runs (score_policy_version `scoring-baseline-v1`) return a typed
`explanation_unavailable` error instead of fabricating reasons (clarification
2026-08-07; FR-018).

**Rationale**: Everything the explanation needs is persisted per run
(evaluations + run snapshots), so generation is cheap, deterministic and
always consistent with what was scored; templates give copy review a single
place.

**Alternatives considered**: (a) persisting the generated explanation at run
time — rejected, redundant since inputs are immutable; (b) LLM redrafting —
rejected by clarification (no generative text in v1).

## R-09 — New HTTP surface: explanations and comparisons, deny-by-default

**Decision**: Three additive product endpoints on the existing protected
surface (pattern of `routers/matches.py`):

- `GET /api/v1/search-profiles/{id}/explanations/{listing_id}?run_id=` — one
  listing explanation; listings outside the run or legacy runs return typed
  problems (`explanation_unavailable`, not_found/forbidden by ownership).
- `GET /api/v1/search-profiles/{id}/explanations?run_id=&page_size=&after_position=`
  — paginated explanations for the run (drives cards).
- `POST /api/v1/search-profiles/{id}/comparisons` `{listing_ids}` — validates
  limit, same-run membership and returns the structured matrix.

OpenAPI regenerated and the TS client committed (`npm run api:generate
--workspace @umbral/web`), per the H1.4/H1.5 convention. Access follows
`product.matches.read`-style actions with `access_control.authorize`
(FR-014/FR-015).

**Rationale**: UM-H3-019 mandates exposing per-listing and per-search
explanations; the web stories (UM-H3-021/022) require contracts. The typed
problem + deny-by-default pattern already exists in the matches router.

**Alternatives considered**: (a) no HTTP surface (like H3.1) — rejected: H3.2
has explicit APP and WEB stories that need product contracts; (b) exposing raw
run internals — rejected, DTOs stay product-shaped.

## R-10 — Comparison: fixed + profile dimensions, limit, no winner

**Decision**: `compare_listings(profile, run, listing_ids, policy,
shortlist_limit) -> Comparison` validates 2..limit listings (default 6,
setting `scoring.comparison_max_listings`) all belonging to the latest
published run of the profile (FR-016/FR-017). Dimensions: fixed basics
(total cost, expensas, surface, rooms, dormitorios, neighborhood/precision,
score + confidence) plus the profile's active criteria from the run's
evaluations (value, evidence, missing per cell). Missing cells render as
missing, never as zero or mismatch; no winner is computed (US8.5). The
`comparison_shortlists` table (P1) persists the selection per profile with
unique (profile_id, listing_id).

**Rationale**: The clarification fixed the dimension mix; run membership is the
ownership boundary; the limit is a setting so product can tune it without
schema change.

**Alternatives considered**: (a) comparing any listings of the radar, not only
run members — rejected, only scored listings have evaluations to show;
(b) winner/aggregate row — rejected by policy of evidence.

## R-11 — Two additive events on the closed registry

**Decision**: `recommendation.explanation_viewed.v1` (client) and
`recommendation.comparison_viewed.v1` (client) registered additively in
`contracts/events/v1/events-registry.json`. Payloads carry
ids/run versions/counts only, never evaluation values, evidence or listing
text (FR-021, SC-010). Runs and evaluations keep emitting via the existing
`recommendation.run_published.v1`.

**Rationale**: The registry is closed and versioned (H1.4/H3.1 convention);
views are the only new signal this increment needs for measurement.

**Alternatives considered**: (a) events per evaluation — rejected, run_published
already carries counts; (b) no view events — rejected, FR-021 explicitly
requires views of explanations and comparisons to emit events.

## R-12 — Performance targets are inherited or plan-level

**Decision**: The `< 30 s` run publish target of H2.3 is inherited unchanged
(the run pipeline is the same; the candidate set is bounded by the controlled
beta dataset). Explanations and comparisons are computed on demand from the
frozen run; plan-level target: p95 < 1 s over the harness dataset. Neither is
a spec success criterion (SC list has none for latency).

**Rationale**: The spec explicitly defers latency to the plan; the inheritance
is documented here so tasks can add a perf smoke without inventing gates.

**Alternatives considered**: new strict SC in the spec — rejected, spec was
frozen after clarify; this stays plan-level.

## R-13 — Web: reasons on cards and detail, legacy notice, comparator P1

**Decision**: The radar list/detail reuse the existing slices
(`app/(protected)/radar/[id]/page.tsx`, `listings/[id]/page.tsx`) and consume
the two explanation endpoints via TanStack Query. Cards show up to 3 top
reasons with evidence-level badges; the detail shows the full breakdown
(reasons, risks, missing data, confidence), never scores as certainty. Legacy
runs show the score without breakdown plus an "explicación no disponible"
notice (clarification 2026-08-07). The comparator (P1) is a dedicated route
with a persistent shortlist per radar and a responsive matrix
(`comparison-v1.md`). Accessibility by project convention (keyboard, labels,
contrast; dedicated axe e2e remains a H2.3 deferred follow-up).

**Rationale**: UM-H3-021/022 are WEB stories with explicit presentation rules;
the legacy state was fixed by clarification; the matrix follows the
comparison contract.

**Alternatives considered**: server-rendered explanation fragments in the
matches page — rejected, keeps the API the single source of truth.

## Deferred to the plan/tasks

- Exact copy strings for the uncertainty wording (template file, reviewed with
  product per UM-H0-007; placeholder keys defined in the contract).
- The precise seed weights of `scoring-policy-v1` (product curation; the
  contract defines the shape, the seed JSON defines the values, defaulted to
  budget/ambientes/superficie/ubicacion as criteria plus the curated subjective
  concepts with small weights).
- Confidence thresholds for strong/medium/low evidence levels (policy
  document; defaulted 0.8/0.5).
- Rate limits: none new (existing API/access control); comparisons are
  synchronous and bounded by the run size.
