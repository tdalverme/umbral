# Quickstart: Calidad del matching (H3.4)

**Feature**: `008-matching-quality` | **Date**: 2026-08-09

Validation guide for the increment. Full contracts:
[matching contracts](./contracts/matching-contracts-v1.md); data shape in
[data-model.md](./data-model.md).

## Prerequisites

- `.venv` activated; `006-scoring-explanations` merged (runs v1, breakdowns,
  explanations) and `005-criteria-observations` (concepts, matcher types,
  compilations).
- `.\scripts\check.ps1` passes before starting.

## Scenario 1 — Dataset golden y contratos (FR-001/FR-002, SC-001)

```powershell
uv run pytest tests/contract/test_matching_golden.py
```

Expected: `golden-dataset-v1.json` validates against its schema, every case
has well-formed expected ranking and hard-filter expectations, coverage rules
hold (at least one case per tag: hard_filter_violation, unknown,
subjective_preference, price_boundary, legacy_no_breakdown) and every id in
expected_ranking exists in listings.

## Scenario 2 — Regresiones de scoring con gate estricto (FR-003..FR-005, SC-002/SC-003)

```powershell
uv run pytest tests/contract/test_matching_regression.py tests/unit/application/matching/test_regression.py
```

Expected (clarifications 2026-08-09): running the same cases under the
baseline policy version vs a candidate version reports per-case verdicts; any
relative order change or hard filter difference blocks the gate unless a
release in `releases-v1.json` declares exactly the affected case ids with
owner and justification; score deltas without order change are informational
and do not block; an induced parser regression (no release) blocks with the
diff listed.

## Scenario 3 — Fidelidad de explicaciones (FR-006/FR-007, FR-012, SC-004)

```powershell
uv run pytest tests/contract/test_matching_fidelity.py tests/unit/application/matching/test_fidelity.py
```

Expected: claims are classified as `supported` (maps to a breakdown entry with
evidence ref), `unsupported` (no breakdown entry) or `contradiction` (conflicts
with the breakdown); unknown/low-confidence cases must declare uncertainty;
the aggregate gate is strict — a single unsupported or contradictory claim
fails; legacy items without breakdown are reported `no_breakdown` and never
fail with fabricated reasons.

## Scenario 4 — Fairness y lenguaje geografico (FR-008/FR-009, SC-005)

```powershell
uv run pytest tests/contract/test_matching_fairness.py
```

Expected: `forbidden-features-v1.json` validates; every forbidden concept is
`computable: false` in the concepts seed and the compiler rejects
compilations referencing them; the normative-phrases scan finds 0 forbidden
phrases in explanation/comparator templates; the fairness review document
exists and is referenced.

## Scenario 5 — Harness y cierre (FR-010/FR-011, SC-006)

```powershell
uv run pytest tests/contract/test_matching_harness.py
.\scripts\check-matching.ps1
.\scripts\check.ps1
```

Expected: the harness builds the golden dataset, runs regressions and fidelity,
reports the fairness state and produces audit reports without PII; 0 product
events, 0 endpoints and 0 migrations are added by this increment; the harness
is registered in `check.ps1` and runs green from the repo root.

## Resultado verificado 2026-08-09

- Los 5 escenarios pasan con `.\scripts\check-matching.ps1` (43 tests).
- `golden-dataset-v1.json` cubre las 5 categorías requeridas con 5 casos
  revisados por producto.
- `run_regression` con la misma policy como baseline/candidata pasa sin
  cambios; una candidata que altera pesos bloquea salvo release declarada con
  los cases coincidentes; un release con case ids divergentes bloquea.
- `evaluate_fidelity` pasa sobre el case golden `match_and_unknown` de H3.2 y
  distingue supported/unsupported/contradiction con threshold estricto; legacy
  se reporta `no_breakdown`.
- `forbidden-features-v1.json` enlaza `barrio_seguro` a `computable: false` en
  el seed; el compilador rechaza compilaciones que lo referencien y el escaner
  de frases normativas pasa sobre los templates.
- Settings `matching.golden_dataset_version` (`golden-dataset-v1`) y
  `matching.regression_gate_enabled` (true) validados.
- Evidencia consolidada: `docs/runbooks/evidence/matching-quality-acceptance.md`.
