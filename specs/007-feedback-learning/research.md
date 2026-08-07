# Research: Feedback y aprendizaje controlado (H3.3)

**Feature**: `007-feedback-learning` | **Date**: 2026-08-07 | **Spec**:
[spec.md](./spec.md)

Decisions and rejected alternatives for UM-H3-023 through UM-H3-031, grounded
in the existing codebase (radar H2.3, criteria H3.1, scoring H3.2).

## R-01 — Feedback events: append-only chain with a derived decision state

**Decision**: `feedback_events` is an append-only table. Each user action
(like, dislike, save, dismiss, contacted) inserts a row with actor, context
(profile, listing, run when it exists), timestamp, idempotency key and an
`active|superseded` state. A decision change supersedes the active row for
(profile, listing) and inserts a new one in the same transaction, storing
`superseded_by` on the old row (traceable compensation chain, FR-003/FR-004).
The **current decision state** is the active row; a partial unique index
`(profile_id, listing_id) WHERE state='active'` guarantees one state per
listing (the `uq_preference_facts_active` pattern of H3.1).

**Rationale**: The spec requires immutable events (FR-001/FR-002), idempotent
recording (FR-003) and traceable compensation on decision change (FR-004). The
preference-facts supersede pattern already exists, is tested and audited.

**Alternatives considered**: (a) mutable decision columns on the listing or
match — rejected, breaks append-only audit; (b) state derived by scanning the
whole chain at read time — rejected, the active index makes the state O(1)
while keeping the full history.

## R-02 — Reasons are normalized children rows linked to concepts

**Decision**: `feedback_event_reasons` child table: (event_id, reason_key,
concept_id nullable, polarity). A curated, versioned quick-reason registry
(`contracts/feedback/v1/quick-reasons-v1.json`) defines keys, labels,
polarity, `concept_key` (optional) and `allowed_on` actions; unknown keys are
rejected at record time with a typed error (FR-006). Concept linkage enables
the signal queries of the learning policy without JSONB gymnastics.

**Rationale**: FR-006 requires curated, versioned, optional reasons with
optional concept references; a child table makes the "events by concept within
a window" scan (learning signals) indexable and keeps events free of denormalized
concept copies.

**Alternatives considered**: (a) reason keys + concepts as a jsonb array on the
event — rejected, signal scans would need GIN-over-jsonb and lose referential
integrity; (b) reasons as free text — rejected, the spec requires curated
categories.

## R-03 — Quick reasons are a versioned seed contract, not a table

**Decision**: The curated reason set lives in a versioned contract file
(`quick-reasons-v1.json`, `registry_version: quick-reasons-v1`,
`contract_version: 1`) loaded at startup by a contract loader, like
`concepts-seed-v1.json` (H3.1) and `scoring-policy-v1.json` (H3.2). The seed
version is a setting (`feedback.quick_reasons_seed_version`). Events reference
immutable reason keys; seed evolution appends new keys or versions without
mutating used ones.

**Rationale**: "Categorias curadas y versionadas" (FR-006) is satisfied by a
versioned seed with startup validation, without a new registry table for a
small curated list; the seed pattern is the established precedent.

**Alternatives considered**: (a) `quick_reasons` + `quick_reason_versions`
tables — rejected as over-engineering for ~8 curated keys; (b) hardcoded list
in code — rejected, must be validated at the contract boundary like every
curated input.

## R-04 — Learning signals are reasoned like/dislike events only

**Decision** (clarification 2026-08-07): only like/dislike events that carry
at least one reason linked to a concept count as learning signals. Save,
dismiss and contacted record state and evidence but never generate proposals
(FR-009). Signal polarity comes from the event type (like=positive,
dislike=negative); the reason's polarity must be consistent with the action
(validated via the reason registry `allowed_on`/polarity). Every signal has
confidence 1.0 (a deliberate reasoned action); the policy's
`min_signal_confidence` (default 1.0) is enforced by construction and remains
a documented policy field for future weaker signals.

**Rationale**: The clarification fixed the signal universe; concept + polarity
are the only inputs the deterministic rule needs, keeping the engine pure and
LLM-free (FR-009).

**Alternatives considered**: (a) save/dismiss/contacted as signals — rejected
by clarification; (b) inferring polarity from reason only — rejected, event
type is the explicit intent.

## R-05 — Learning policy persists like the scoring policy (append-only versions)

**Decision**: `learning_policies` + immutable `learning_policy_versions`
mirroring `scoring_policies`/`scoring_policy_versions`. The payload is a JSONB
document validated against `contracts/learning/v1/learning-policy-v1.json`
(min_signals, window_days, min_signal_confidence, cooldown_days,
proposal_expiration_days, default_suggested_weight, default_suggested_confidence).
The curated seed `learning-v1` is loaded at startup
(`learning.policy_seed_version`). Proposals record the policy version that
produced them.

**Rationale**: FR-009 requires a versioned, immutable sufficiency rule with
cooldown and expiration; the scoring policy registry is the tested precedent,
and proposals must be auditable against the rule that created them.

**Alternatives considered**: (a) flat settings as the rule — rejected, the rule
must be immutable per proposal for audit (same reasoning as R-02 of H3.2);
(b) thresholds only in code — rejected, not versionable.

## R-06 — v1 proposals are preference-fact adjustments; criterion proposals deferred

**Decision**: A proposal is `{kind: "preference_fact", concept_key, polarity,
suggested_weight, suggested_confidence, value: None}` with evidence refs to the
feedback events. Confirming records a preference fact through
`CriteriaService.record_preference_fact(fact_source="learning.proposal")` with
`value=None` (the fact adjusts weight/polarity/confidence of the existing
preference without inventing a concrete value), then recompiles and re-runs.
Proposals of kind `criterion` are reserved in the contract but not produced in
v1: deriving matcher params from signals alone would require inventing values,
which violates the evidence policy (UM-H0-007).

**Rationale**: Preference facts carry exactly what signals provide (concept,
polarity, strength) and fit the H3.1 fact model; the spec allows "preference
fact o criterio" (either); deferring criteria keeps the engine honest.

**Alternatives considered**: (a) criterion proposals with guessed params —
rejected, invents evidence; (b) value inferred from signal statistics — rejected,
statistical guessing on small samples violates the no-trend/evidence rules.

## R-07 — Proposal evaluation runs synchronously in the feedback service

**Decision**: After a reasoned like/dislike is recorded, the service evaluates
signals for each concept of the event's reasons: count active reasoned events
of the same polarity within `window_days`, and if `>= min_signals`, no pending
or confirmed proposal for (profile, concept) inside `cooldown_days` and none
pending (partial unique), create a pending proposal. This scan is bounded (one
profile, a few concepts) and synchronous; no new job type.

**Rationale**: Proposals must feel immediate (the web banner surfaces them on
the radar), and the volume is tiny in beta; a job would add latency and
complexity for no need (FR-009, US3).

**Alternatives considered**: (a) a `learning.propose` job — rejected, extra
scheduler surface without volume; (b) evaluation only at radar load — rejected,
the banner would appear nondeterministically.

## R-08 — Confirmation reuses the existing fact/compile/run seams; trigger "edited"

**Decision**: `FeedbackService.confirm_proposal` orchestrates existing public
seams: `CriteriaService.record_preference_fact` (supersedes the active fact) →
`RadarService.bump_profile_version` (new small seam: loads profile, bumps
version, snapshots, without submitting) → `CriteriaService.compile_profile`
against the new version → `RadarService.submit_run(profile, version,
trigger="edited")` (the H3.2 `_submit_run` path exposed as a public method).
The `recommendation_runs.trigger` ENUM is NOT extended: confirmed-learning runs
reuse `edited` (no migration). Undo records a compensating fact restoring the
pre-confirmation fact values, then the same bump/compile/run sequence.

**Rationale**: Everything needed already exists and is tested; the two new
public seams are minimal additions mirroring `update_profile` internals.
Compile must happen after the version bump and before the run submission so
the run's compilation exists when the worker picks it up (FR-012/FR-014).

**Alternatives considered**: (a) a new trigger ENUM value `learning` — rejected,
schema churn without product value; (b) reusing `update_profile` with edits —
rejected, profile validation is for structured edits, not learning facts.

## R-09 — Undo and reject are first-class proposal transitions

**Decision**: Proposals transition pending → confirmed | rejected | expired |
superseded. `undo` on a confirmed proposal records a compensating preference
fact with the pre-confirmation values (read from the fact chain),
bump/compile/run again, and marks the proposal `superseded` referencing the
undo action; the intermediate run stays consultable (FR-012, US4.4). Expiry is
lazy: reads and confirm evaluate `expires_at`; a confirm on an expired proposal
rejects it with a typed error and flips the state to `expired` with an event
(no sweep job).

**Rationale**: The spec requires reversible decisions with traceable
compensation (FR-012) and expiration without inventing a janitor job.

**Alternatives considered**: (a) physical rollback of the confirmed fact —
rejected, facts are append-only by H3.1; compensation is the audit pattern;
(b) a daily sweep job for expiry — rejected, lazy transition on access is
sufficient for beta volume.

## R-10 — Shortlist persistence is shared: save event writes comparison_shortlists

**Decision**: The H3.3 shortlist view reads `comparison_shortlists` (H3.2 P1
table), honoring the spec assumption that H3.3 views consume the same
persistence. A `save` action writes the feedback event AND upserts the
comparison_shortlists row (position = tail); un-save (supersede) removes the
row. `FeedbackService` reaches the table through its own port using the
existing `SqlAlchemyShortlistRepository` adapter (extended with `add`/`remove`
methods; `replace` stays for the comparator). The P1 comparator gate
(`scoring.comparator_enabled`) keeps gating the comparisons/shortlist
endpoints and the matrix UI; the H3.3 shortlist view reads the table without
the gate (P0, UM-H3-026). Dismissed items are hidden from the radar default
view by a state overlay at query time (matches endpoint annotates
`decision_state` and accepts `include_dismissed=false` default); 0 runs are
created by direct feedback (FR-015).

**Rationale**: One persisted shortlist serves both the product view (P0) and
the comparator (P1); the overlay honors FR-015 (no runs on direct feedback)
and FR-008 (hidden by default, filterable).

**Alternatives considered**: (a) a second shortlist table for save state —
rejected, duplicates the persistence the H3.2 assumption already shares;
(b) re-running the engine on every dismiss — rejected by FR-015.

## R-11 — Price history is served by existing listing-change data

**Decision**: UM-H3-031 (P1) consumes the existing `listing_changes` data
(price and attribute changes with before/after, date and source) that the
detail DTO already exposes as `known_changes`; the web detail gains a history
section with dates and sources, declaring "historial insuficiente" when there
is no sample and drawing 0 trend lines (FR-017). No new backend surface
beyond the existing detail payload (additive fields if needed).

**Rationale**: H2.2 already records changes between versions; the spec only
requires honest display, not new capture.

**Alternatives considered**: (a) a dedicated `/listings/{id}/changes`
endpoint — rejected, the detail DTO already carries the data; (b) trend
inference — rejected by FR-017.

## R-12 — HTTP surface: feedback, decision items, proposals; deny-by-default

**Decision**: Additive endpoints on the protected surface (pattern of
`routers/matches.py`/`explanations.py`):

- `POST /api/v1/search-profiles/{id}/feedback` — record an action
  (idempotency key, listing, optional run, reasons, free feedback P1);
  returns the event + decision state; no-op and supersede semantics; typed
  errors (`feedback_not_found`, `feedback_terminal` (contacted),
  `feedback_invalid_reason`, `feedback_conflict`).
- `GET /api/v1/search-profiles/{id}/decision-items?decision_state=&page_size=&after_position=`
  — saved/dismissed/liked/disliked/contacted views (drives shortlist +
  dismissed screens).
- `GET /api/v1/search-profiles/{id}/matches` — additive `include_dismissed`
  param and `decision_state` annotation per item (radar default hides
  dismissed; FR-008).
- `GET /api/v1/search-profiles/{id}/learning-proposals?state=` — pending/
  history list; `POST .../{proposal_id}/confirm|reject|undo`,
  `PUT .../{proposal_id}` (expand) — typed problems (`proposal_not_pending`,
  `proposal_not_found`, `proposal_expired`).

OpenAPI regenerated and the TS client committed per the H1.4/H1.5 convention;
the web pages keep using the hand-typed `lib/radar/client.ts` additions
(current web convention). Access actions `product.feedback.write`,
`product.feedback.read`, `product.learning.read|write` via
`access_control.authorize` (FR-019).

**Rationale**: The web stories (UM-H3-025/026/027/029/031) require product
contracts; the typed-problem and deny-by-default patterns already exist.

**Alternatives considered**: (a) separate endpoints per state — rejected, one
filtered list endpoint is simpler; (b) mutating the matches response schema
with breaking changes — rejected, additions are additive.

## R-13 — Event surface: additive server + client types

**Decision**: Additive types in the closed registry
(`contracts/events/v1/events-registry.json`): server
`feedback.recorded.v1`, `learning.proposal_created.v1`,
`learning.proposal_confirmed.v1`, `learning.proposal_rejected.v1`,
`learning.proposal_expanded.v1`, `learning.proposal_undone.v1`,
`learning.proposal_expired.v1`; client `feedback.shortlist_viewed.v1`,
`feedback.dismissed_viewed.v1`. Payloads carry ids/state/counts only; free
feedback text NEVER enters events or analytics (FR-016/FR-018, SC-008). Event
emission reuses the existing `_emit_server_event`/`record_client_event`
patterns.

**Rationale**: FR-018 requires feedback, proposals, confirmations and views to
emit versioned events; the registry is closed and additive by convention
(R-11 of H3.2).

**Alternatives considered**: (a) one coarse `feedback.updated.v1` — rejected,
loses audit granularity per transition; (b) embedding free text — rejected,
PII/SC-008.

## R-14 — Web: card/detail actions, views, banner; P1 gates

**Decision**: Radar cards and listing detail gain save/dismiss/like/dislike +
quick reasons with optimistic, reversible states (undo available except
contacted; FR-005) using the existing shadcn primitives (`button`, `card`,
`alert`, `skeleton`); the radar page renders the pending-proposal banner
(inline, with confirm/expand/dismiss actions and link to proposal detail;
clarification 2026-08-07, FR-013); new `radar/[id]/shortlist` and
`radar/[id]/dismissed` views (filters + navigation to detail); free feedback
capture (P1, `feedback.free_feedback_enabled=false`) and the price history
section (P1, from `known_changes`). Accessibility by project convention
(keyboard, labels, contrast). Web events via the existing
`lib/radar/events.ts` emitter.

**Rationale**: UM-H3-025/026/029 are P0 web stories with explicit rules; P1
stories are flag-gated so the first internal pass stays unblocked.

**Alternatives considered**: server-rendered feedback states — rejected, the
API remains the single source of truth and optimistic UX requires local state.

## Deferred to the plan/tasks

- Exact values of `learning-v1` policy (min_signals=3, window_days=90,
  min_signal_confidence=1.0, cooldown_days=7, proposal_expiration_days=30,
  suggested weight/confidence defaults) — product curation in the seed file.
- The exact quick-reason set labels/copy (reviewed with product per UM-H0-007;
  keys defined in the contract).
- Free feedback length limit (default 500 chars) and price-history copy.
- Rate limits: none new (existing API/access control); feedback writes are
  synchronous and bounded per request.
