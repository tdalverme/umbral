# Evidencia de cierre: Calidad del matching (H3.4)

**Incremento**: `008-matching-quality` | **Fecha**: 2026-08-09

## Alcance

UM-H3-032 a UM-H3-035 (Epica H3.4 - Calidad del matching), según el spec
`specs/008-matching-quality/spec.md` con las clarificaciones 2026-08-09 (gate
estricto de regresiones, release con casos coincidentes, threshold estricto de
fidelidad).

## Resultado por SC

- **SC-001 (dataset golden)**: PASS. `contracts/matching/v1/golden-dataset-v1.json`
  cubre las 5 categorías requeridas (hard_filter_violation, unknown,
  subjective_preference, price_boundary, legacy_no_breakdown) con 5 casos
  revisados por producto (`reviewed_by`/`reviewed_at`). Conformance en
  `tests/contract/test_matching_golden.py`.
- **SC-002/SC-003 (regresiones con gate estricto)**: PASS. `run_regression`
  compara baseline vs candidata sobre el dataset; cualquier cambio de orden
  relativo o de hard filters bloquea salvo release declarada con cases
  coincidentes; score deltas sin cambio de orden son informativos. Unit en
  `tests/unit/application/matching/test_regression.py` y conformance
  `tests/contract/test_matching_regression.py`.
- **SC-004 (fidelidad de explicaciones)**: PASS. `evaluate_fidelity` clasifica
  claims como supported/unsupported/contradiction contra el breakdown de H3.2,
  verifica incertidumbre y aplica threshold estricto; legacy se reporta
  `no_breakdown`. Unit en `tests/unit/application/matching/test_fidelity.py` y
  conformance `tests/contract/test_matching_fidelity.py`.
- **SC-005 (fairness y lenguaje geografico, P1)**: PASS.
  `contracts/matching/v1/forbidden-features-v1.json` +
  `docs/product/fairness-review-v1.md`; `barrio_seguro` es `computable: false`
  en el seed y el compilador rechaza compilaciones que lo referencien;
  escaner de frases normativas pasa sobre templates. Conformance en
  `tests/contract/test_matching_fairness.py` y
  `tests/unit/application/criteria/test_compile_forbidden_concepts.py`.
- **SC-006 (harness y report)**: PASS. `scripts/check-matching.ps1` registrado
  en `check.ps1`; reportes sin PII; 0 endpoints, 0 eventos de producto, 0
  migraciones nuevas. Conformance en `tests/contract/test_matching_harness.py`.

## Recorrido de quickstart

Los 5 escenarios de `specs/008-matching-quality/quickstart.md` pasan con el
harness y pytest dedicado (43 tests en `check-matching.ps1`).

## Detalles de implementacion

- Nuevo modulo puro y test-only `src/umbral/application/matching/`
  (`contracts.py`, `golden.py`, `releases.py`, `regression.py`, `fidelity.py`,
  `fairness.py`, `report.py`).
- Contratos versionados bajo `contracts/matching/v1/` (+ schema JSON del golden
  dataset).
- Flag aditivo `compute_policy.computable` en el concepts seed (default true)
  con enforcement en el compilador (`criteria.concept_not_computable`) y
  exclusion de conceptos no computables de la extraccion full-scope.
- Settings `matching.*` (`golden_dataset_version`, `regression_gate_enabled`).
- 0 migraciones, 0 endpoints, 0 eventos, 0 superficies web.

## Verificaciones

```powershell
.\scripts\check-matching.ps1          # PASS (43 tests)
uv run ruff check .                   # limpio en la superficie del incremento
uv run mypy src tests                 # limpio en el modulo matching y criteria
```

Nota: la suite completa tiene 2 fallos pre-existentes ajenos al incremento
(`tests/unit/workers/test_cli.py`, `tests/contract/test_supabase_adapter.py`) y
errores de collection por basename duplicado `test_lineage.py`
(feedback/scoring/silver), no introducidos por este incremento.
