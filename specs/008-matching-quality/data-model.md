# Data Model: Calidad del matching (H3.4)

**Feature**: `008-matching-quality` | **Date**: 2026-08-09

This increment adds NO database tables and NO migration. All new data lives in
versioned contract files under `contracts/matching/v1/` plus the additive
`computable` flag on the concepts seed (H3.1 contract, validated at load; no
schema migration because the seed is a JSON contract, not a table).

## Contract files

### golden-dataset-v1.json

Versioned, immutable golden recommendation dataset (UM-H3-032, R-01).
JSON Schema `contracts/matching/v1/golden-dataset.schema.json`; registry
identifier `golden-dataset-v1`; `contract_version: 1`.

| Field | Type | Notes |
| --- | --- | --- |
| contract_version | string | `1` |
| registry_version | string | `golden-dataset-v1` |
| reviewed_by | string | product reviewer / session reference |
| reviewed_at | date | product review date |
| baseline_score_policy_version | string | policy version the expected orders were reviewed against (e.g. `scoring-policy-v1`) |
| cases | array | each case is a self-contained scenario |

Each case:

| Field | Type | Notes |
| --- | --- | --- |
| id | string | stable case id, e.g. `golden-001` |
| tags | array<string> | `hard_filter_violation`, `unknown`, `subjective_preference`, `price_boundary`, `legacy_no_breakdown`, ... |
| profile_criteria | object | compilation input: criteria with matcher type + params (H3.1) |
| listings | array | candidate listings with observations/features needed by the evaluators (H3.2 input) |
| expected_ranking | array<string> | listing ids in expected order under `baseline_score_policy_version` |
| expected_hard_filter | object | which candidates pass/fail hard filters under the policy |
| notes | string optional | curator context, no runtime semantics |

Validation rules (conformance): ids unique; every expected_ranking id exists in
listings; expected order covers all non-filtered listings; tags have known
values; profile criteria validate against `matcher-types-v1.json`; at least one
case per required tag category (SC-001 coverage).

### releases-v1.json

Versioned registry of explained scoring changes (UM-H3-033, FR-005, R-02).
Registry identifier `matching-releases-v1`; `contract_version: 1`.

| Field | Type | Notes |
| --- | --- | --- |
| contract_version | string | `1` |
| registry_version | string | `matching-releases-v1` |
| releases | array | append-only entries |

Each release entry:

| Field | Type | Notes |
| --- | --- | --- |
| id | string | e.g. `rel-001` |
| artifact | string | `scoring.policy` \| `criteria.concept` \| `extraction.rule` \| `extraction.prompt` |
| artifact_version | string | new version identifier, e.g. `scoring-policy-v2` |
| owner | string | responsible person |
| justification | string | why the change is intentional |
| affected_case_ids | array<string> | golden cases whose expected behavior changes (must match the regression diff) |
| date | date | |

Validation rules: ids unique; artifact_version unique; affected_case_ids exist
in the golden dataset; at least one release entry when the regression detects
order changes (FR-005).

### forbidden-features-v1.json

Machine-checkable output of the fairness review (UM-H3-035, FR-008, R-05).
Registry identifier `forbidden-features-v1`; `contract_version: 1`.

| Field | Type | Notes |
| --- | --- | --- |
| contract_version | string | `1` |
| registry_version | string | `forbidden-features-v1` |
| forbidden_concepts | array | concept keys marked non-computable (must also be `computable: false` in the concepts seed) |
| forbidden_proxies | array | proxy feature descriptions with justification |
| normative_phrases | array | copy phrases that must never appear in templates |

Each forbidden concept:

| Field | Type | Notes |
| --- | --- | --- |
| concept_key | string | key from `concepts-seed-v1.json` |
| justification | string | reason (sensitive inference, discriminatory proxy, normative claim) |

## Additive concepts-seed change

`contracts/criteria/v1/concepts-seed-v1.json` gains an optional
`compute_policy.computable` boolean (default `true` when absent) on each
concept. Concepts listed in `forbidden-features-v1.json` set
`computable: false`. The criteria registry parser (H3.1) exposes the flag; the
criteria compiler and the regression runner reject any compilation referencing
a non-computable concept. This is a contract change (new additive field), not
a DB migration: seed files are loaded and validated at startup by the existing
contract loader (R-05).

## State transitions

- Regression run: `passing` / `blocked` — blocked when any relative order
  change or hard filter difference is not declared in `releases-v1.json`
  (FR-004/FR-005). The report lists per-case verdicts: `ok`, `order_change`,
  `hard_filter_change`, `score_delta_informational`.
- Fidelity verdict per claim: `supported`, `unsupported`, `contradiction`,
  `uncertainty_declared`, and per item `no_breakdown` (legacy, R-04). Aggregate
  `passing` requires 100% supported, 0 unsupported, 0 contradictions (FR-007).
- Fairness review: `open` / `reviewed` — reviewed when
  `fairness-review-v1.md` and `forbidden-features-v1.json` are committed and
  the conformance checks pass (FR-008/FR-009).

## Volume and scale assumptions

- Golden dataset v1: on the order of tens of cases (one per tag category, plus
  boundary variants), reviewed by product per version; the exact count and
  values are curated in the contract by product during implementation without
  changing the schema.
- Releases and forbidden features are small append-only lists.
- All structures are harness-time data: no runtime query volume, no indexes
  beyond file validation.
