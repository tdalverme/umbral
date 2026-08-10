# Research: Calidad del matching (H3.4)

**Feature**: `008-matching-quality` | **Date**: 2026-08-09 | **Spec**:
[spec.md](./spec.md)

Decisions and rejected alternatives for UM-H3-032 through UM-H3-035, grounded
in the existing codebase (criteria H3.1, scoring H3.2, feedback H3.3, harness
conventions).

## R-01 — The golden dataset is a versioned contract, not a DB table

**Decision**: The golden recommendation dataset lives as a versioned, immutable
contract file `contracts/matching/v1/golden-dataset-v1.json` (JSON Schema +
conformance tests), mirroring `concepts-seed-v1.json` (H3.1) and
`scoring-policy-v1.json` (H3.2). Each case is self-contained: profile criteria
(compilation input), candidate listings with their observations/features,
context markers (hard filter violation, unknown, subjective preference, price
boundary) and the expected ranking order plus a `score_policy_version` that
states the policy revision under which product reviewed it. The regression
runner executes the pure H3.2 engine over this fixture data — no DB, no LLM,
no workers.

**Rationale**: UM-H3-032 demands a curated, versioned, product-reviewed
reference. The contract-file pattern is the established precedent for
versioned, immutable, machine-checkable inputs (seed contracts), and a
self-contained fixture set keeps the regression runner pure and fast in CI
without a live database. Immutability comes from the file being a reviewable,
committed artifact plus the conformance gate on any change.

**Alternatives considered**: (a) golden dataset as DB tables
(`golden_cases`/`golden_expected_orders`) — rejected, adds migration and
runtime surface for data that never changes at runtime and is only read by the
harness; (b) fixture JSON under `tests/fixtures` only — rejected, the dataset
is a product contract (reviewed by product, referenced by releases) and
belongs under `contracts/` like every other curated contract; `tests/fixtures`
keeps generated/synthetic variants.

## R-02 — Regression compares policy revisions over the same cases; releases explain diffs

**Decision**: The regression runner (`application/matching/regression.py`)
compares, per golden case, the ranking produced by the policy revision the
case was reviewed against (`case.score_policy_version`) with the ranking
produced by a candidate revision loaded as a seed file. A relative order
change on any case is a hard failure; hard filter results are always compared
(strict gate, clarification 2026-08-09); score deltas that do not change order
are informational rows in the report. An intentional, documented change is
declared in `contracts/matching/v1/releases-v1.json`: each entry names the
artifact version (policy/parser/prompt/concept), the owner, the justification
and the affected case ids. The harness fails unless every order-changed case
is declared in a release entry whose stated cases match the detected ones
(clarification 2026-08-09, FR-004/FR-005).

**Rationale**: The gate is verifiable only if "explained" is checked
mechanically. Binding the explanation to a versioned release manifest with
case-level claims makes the check automatic (no free-text bypass) and keeps
the audit trail in the same versioned contract world as everything else.

**Alternatives considered**: (a) free-text "reason" field in the harness run
report — rejected by clarification 2026-08-09 (no free-text explanation,
verification against the real diff); (b) human approval outside the harness —
rejected, adds a workflow seam the project does not have and blocks CI on a
person; (c) embedding releases inside the golden dataset file — rejected, the
dataset is product-reviewed truth and should not mutate when a release is
registered; a sibling manifest keeps both files append-only.

## R-03 — Fidelity is measured deterministically over the persisted breakdown

**Decision**: `application/matching/fidelity.py` is a pure evaluator that takes
a scored item's persisted `ScoringBreakdown` (H3.2 criterion evaluations +
evidence refs) and its rendered explanation, and returns per-claim verdicts:
`supported` (claim maps to a breakdown entry with an evidence ref), `unsupported`
(no matching breakdown entry) and `contradiction` (claim conflicts with the
breakdown), plus an `uncertainty_declared` check (unknown/low-confidence items
must be stated). Aggregate pass requires 100% supported claims, 0 unsupported,
0 contradictions (strict threshold, clarification 2026-08-09, FR-006/FR-007).
In v1 explanations are deterministic templates over the breakdown, so the
evaluator validates the rendering pipeline and any future generative copy must
pass the same check before release (FR-012).

**Rationale**: The spec requires automatic measurement of evidence coverage,
contradictions, unsupported claims and uncertainty copy. The persisted
breakdown is the single source of truth (H3.2); evaluating against it is pure,
fast and needs no LLM judge — which would contradict the deterministic
explanation decision of H3.2 and add cost/instability.

**Alternatives considered**: (a) LLM-as-judge for fidelity — rejected: v1
explanations are deterministic, an LLM judge is nondeterministic, costly and
creates a new model/prompt versioning surface for no gain; (b) golden
expected-explanations only — rejected, it misses the "claims must map to
evidence" property; the evaluator derives verdicts from the breakdown instead
of hand-writing every expectation.

## R-04 — Legacy listings (baseline run, no breakdown) are excluded from strict fidelity

**Decision**: Items whose run carries the legacy baseline score version
(`scoring-baseline-v1`, no persisted breakdown) are reported as
`no_breakdown` and never scored on fidelity; 0 claims are fabricated for them
(FR-007 edge case). The golden dataset has dedicated cases that exercise this
path so the evaluator's classification is covered.

**Rationale**: H3.2 already treats legacy runs as "visible without breakdown";
fidelity must not invent evidence for them.

**Alternatives considered**: (a) treating legacy claims as unsupported —
rejected, that would flag the whole legacy surface as failing without meaning;
(b) migrating legacy items — rejected, out of scope and unnecessary.

## R-05 — Forbidden features are an additive `computable` flag in the concepts seed plus a fairness review document

**Decision**: The fairness review (UM-H3-035, P1) produces two artifacts: (a)
`docs/product/fairness-review-v1.md`, a versioned human document with findings,
reviewed copy and decisions; and (b) a machine-checkable
`contracts/matching/v1/forbidden-features-v1.json` listing forbidden concept
keys and discriminatory proxies with justification. Concepts in the list must
carry `compute_policy.computable: false` in the concepts seed (additive field,
default `true` when absent, so the published seed stays compatible); the
criteria compiler and the regression runner reject any compilation whose
criteria reference a non-computable concept. The copy check is a conformance
test that scans explanation/comparator templates for forbidden normative
phrases listed in the fairness review.

**Rationale**: FR-008/FR-009 require the registry to document forbidden
features as non-computable and a versioned document, without new
infrastructure. The additive seed field keeps the concept contract stable
while making "non-computable" enforced, not just documented; the fairness
review document carries the narrative evidence.

**Alternatives considered**: (a) separate `forbidden_features` table — rejected,
over-engineering for a curated, rarely-changing list (same reasoning as
quick-reasons R-03 of H3.3); (b) documentation-only without the seed flag —
rejected, enforcement belongs in the same validation path as every other
concept rule; (c) removing forbidden concepts from the seed — rejected, they
must stay discoverable as forbidden, not disappear.

## R-06 — The matching module is pure harness machinery, no runtime wiring

**Decision**: `application/matching/` (golden parser, regression runner,
fidelity evaluator, forbidden-features validation, report builder) is a pure,
test-only surface: it is never imported by `api/` or workers, it does not read
the database at runtime and it is consumed only by `tests/contract/`,
`tests/unit/application/matching/` and the harness script
`scripts/check-matching.ps1`. No new migration, no new endpoints, no new
events, no new settings beyond the golden-dataset seed version
(`matching.golden_dataset_version`, safe default, registered in
`_known_fields`).

**Rationale**: FR-010/FR-011 bound the increment to verification: 0 product
surfaces, 0 product events, 0 endpoints. Keeping the module test-only honors
the dependency direction and the minimal-change principle; the harness surface
mirrors `check-scoring.ps1` (registered in `check.ps1` under a
`matchingSurface` guard).

**Alternatives considered**: (a) a runtime endpoint that returns regression
reports — rejected, violates FR-011 and exposes internal verification to the
API; (b) folding everything into existing scoring tests — rejected, the golden
dataset + releases + fidelity deserve their own conformance surface and harness
gate like every other increment.

## R-07 — Golden dataset version and gate enabled by default

**Decision**: `matching.golden_dataset_version` defaults to `golden-dataset-v1`
and `matching.regression_gate_enabled` defaults to `true`; the harness loads
the seed contract by version. A regression failure is a hard error (exit code
non-zero), never a warning.

**Rationale**: The spec requires the gate to block unexplained changes
(FR-004, SC-002/SC-003); a default-enabled hard gate is the only behavior that
satisfies the guardrail without operator action.

**Alternatives considered**: (a) gate default disabled behind a flag — rejected,
would make the guardrail opt-in and unverifiable; (b) warning-only mode in CI —
rejected, contradicts "bloquea cambios no explicados".
