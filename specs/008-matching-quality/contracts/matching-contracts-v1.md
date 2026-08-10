# Contracts: Calidad del matching (H3.4)

**Feature**: `008-matching-quality` | **Date**: 2026-08-09

All contracts are machine-checkable files under `contracts/matching/v1/`
following the project's versioned-contract convention (registry
identifier + `contract_version`), validated by conformance tests in
`tests/contract/test_matching_*.py`.

## 1. Golden dataset — golden-dataset-v1.json

Versioned reference of recommendation cases with product-reviewed expected
order (UM-H3-032, FR-001/FR-002). Full shape and rules:
[data-model.md](../data-model.md).

Contract file: `contracts/matching/v1/golden-dataset-v1.json`
Schema: `contracts/matching/v1/golden-dataset.schema.json`
Registry version: `golden-dataset-v1`, contract version `1`.

Key rules (enforced by conformance):

- Every case carries `profile_criteria` (valid against
  `contracts/criteria/v1/matcher-types-v1.json`), `listings` with the
  observations/features the H3.2 evaluators need, `expected_ranking`
  (listing ids in expected order), `expected_hard_filter` and `tags`
  (`hard_filter_violation`, `unknown`, `subjective_preference`,
  `price_boundary`, `legacy_no_breakdown`).
- The dataset declares `baseline_score_policy_version`: the policy version the
  expected orders were reviewed against.
- Coverage rule: at least one case per required tag category (SC-001).
- The dataset is immutable once reviewed: changes go through a new version.

## 2. Releases — releases-v1.json

Append-only registry of explained scoring changes (UM-H3-033, FR-005,
clarification 2026-08-09). Every release entry declares `artifact`,
`artifact_version`, `owner`, `justification`, `affected_case_ids` and `date`.
The regression harness blocks unless every detected order/hard-filter change
is declared by a release whose `affected_case_ids` match the detected ones.

Contract file: `contracts/matching/v1/releases-v1.json`
Registry version: `matching-releases-v1`, contract version `1`.

## 3. Forbidden features — forbidden-features-v1.json

Machine-checkable output of the fairness review (UM-H3-035, FR-008, R-05):
`forbidden_concepts` (concept keys that must be `computable: false` in the
concepts seed), `forbidden_proxies` (with justification) and
`normative_phrases` (copy that must never appear in templates). The human
narrative lives in `docs/product/fairness-review-v1.md`.

Contract file: `contracts/matching/v1/forbidden-features-v1.json`
Registry version: `forbidden-features-v1`, contract version `1`.

## 4. Concepts seed additive field — compute_policy.computable

`contracts/criteria/v1/concepts-seed-v1.json` gains an optional
`compute_policy.computable` boolean (default `true` when absent). Concepts in
`forbidden-features-v1.json` must be `computable: false`; the criteria
registry exposes the flag and the compiler/regression runner reject
compilations referencing non-computable concepts (FR-008, R-05). No schema
migration: seed files are validated at load by the existing contract loader.

## Conformance surface

| Test | Validates |
| --- | --- |
| `test_matching_golden.py` | golden dataset structure, coverage, expected orders well-formed (FR-001/FR-002) |
| `test_matching_regression.py` | regression over two policy versions, strict order/hard-filter gate, releases matching (FR-003..FR-005) |
| `test_matching_fidelity.py` | supported/unsupported/contradiction/uncertainty verdicts, legacy no-breakdown, 100% strict threshold (FR-006/FR-007) |
| `test_matching_fairness.py` | forbidden-features contract, seed `computable:false` linkage, normative-phrases scan (FR-008/FR-009) |
| `test_matching_harness.py` | harness wiring: reports without PII, 0 product events/endpoints (FR-010/FR-011) |

No OpenAPI changes: this increment exposes no HTTP surface (FR-011).
