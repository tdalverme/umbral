# Re-review — hardening task 1: grounded narrative integrity

## Spec: PASS

## Quality: PASS

## Strengths

- Geographic packets now carry explicit placement, and managed validation checks match/trade-off/unknown markers against the packet descriptor (`src/umbral/application/scoring/narrative.py:326-340`, `src/umbral/infrastructure/scoring/narrative.py:234-340`). Direct probes rejected both negative-as-match and positive-as-tradeoff cases.
- The unknown-claim case requested in the previous review is closed: the closed-world token check rejects `"Encaja por la buena conectividad y tiene vista al río."` (`src/umbral/infrastructure/scoring/narrative.py:343-371`; probe result `untracked_view_accepted=False`).
- Identity-less and mismatched observation snapshots are now omitted because `listing_id` is required and compared exactly (`src/umbral/application/scoring/service.py:614-623`). The identity-less probe returned `0` rehydrated observations.
- Human labels cover the supported concept set, with no `"esta prioridad"` result in the label probe (`src/umbral/application/scoring/narrative.py:27-64`, `611-614`).
- The endpoint still resolves an omitted run once and reuses that UUID for explanation and narrative (`src/umbral/api/routers/explanations.py:249-266`).
- Train/subte identity remains preserved (`src/umbral/application/scoring/narrative.py:469-479`, `496-515`), unsupported geographic signals remain omitted (`src/umbral/application/scoring/narrative.py:66-75`), and fallback provenance remains limited to rendered facts (`src/umbral/application/scoring/narrative.py:157-195`).
- The engine diff only adds listing identity to the frozen narrative snapshot (`src/umbral/application/scoring/engine.py:273-283`); no scoring formula, ranking, hard-filter, activation, notification, model, or migration changes were introduced.

## Issues

### Blocker

None identified.

### Critical

1. **Resolved in the correction round: closed-world validation was not provenance-complete for authorized but unlisted packets.** `src/umbral/infrastructure/scoring/narrative.py` now scopes lexical authorization to packets whose evidence refs intersect the submitted refs and whose criteria are included in `used_criteria`; price values are similarly gated by the submitted price ref. The exact regression text `"Encaja por la buena conectividad y la superficie."` with only `acceso_transporte` and `urban:transit-1` now falls back.

### Correction-round verification

- RED: the exact authorized-unlisted descriptor regression failed (`1 failed`) before the fix.
- GREEN: the regression passed (`1 passed`) after the minimal packet-scoped authorization change.
- Placement favorable/desfavorable, exact fallback provenance, and managed happy path are covered by the writer tests.
- Focused narrative/contracts suite: **52 passed, 11 warnings**.
- Relevant backend scoring/infrastructure/contracts suite: **131 passed, 11 warnings**.
- Ruff: **passed**.
- Strict mypy over the six changed source/fixture files: **passed**. The broader repository baseline remains documented with 8 unrelated targeted errors and 195 full-baseline errors.
- Web suite: **31 files / 80 tests passed**; TypeScript typecheck **passed**.
- `git diff --check`: **passed**.

### Major

None identified.

### Minor

None identified.

## Tests/commands executed and result

- `PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest tests/unit/application/scoring/test_narrative.py tests/unit/application/scoring/test_narrative_service.py tests/unit/infrastructure/scoring/test_narrative_writer.py tests/contract/test_explanation_endpoints.py tests/contract/test_explanation_narrative.py -q` — **52 passed, 11 warnings**.
- `PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest tests/unit/application/scoring tests/unit/infrastructure/scoring tests/contract/test_explanations.py tests/contract/test_explanation_narrative.py tests/contract/test_explanation_endpoints.py -q` — **131 passed, 11 warnings**.
- Ruff on all changed source and fixture files — **passed**.
- Targeted mypy invocation — **8 errors**, all existing unrelated baseline errors in `src/umbral/application/preferences/service.py`, `src/umbral/agent/graph.py`, and `src/umbral/api/dependencies.py`; no errors were reported in changed narrative source or fixtures.
- `git diff e1f21b1..35d9519 --check` — **passed**.
- Direct probes: negative-as-match **False**; positive-as-tradeoff **False**; unknown extra claim **False**; identity-less observation rehydration **0**; placeholder labels **none**; authorized-unlisted wrong-placement claim **False** after correction.

## Limitations

The focused and relevant backend suites are green and the residual provenance bypass is covered by the correction regression. No full repository suite claim is made; mypy remains red only on unrelated baseline files. The implementation and report changes were committed without publishing or merging.

## Correction commit

`205b90c` — `fix: scope narrative copy to submitted packets`
