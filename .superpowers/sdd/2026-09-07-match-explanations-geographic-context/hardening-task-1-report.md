# Hardening task 1 — grounded narrative integrity

## Status

Complete. Implemented on `feat/match-explanations-geographic-context` from base `e1f21b1`.

## Changes

- Managed narrative output now requires non-empty evidence and validates the claim against the same structured packet fact, active criterion, and submitted evidence reference. Invented price/amenity claims, empty refs, unrelated refs, raw keys, and unsafe copy fall back deterministically.
- Selected explanation requests resolve an omitted `run_id` once and reuse that UUID for the breakdown and optional narrative.
- Geographic facts retain their signal identity and are classified using criterion polarity. Conflicting avoid-style signals become trade-offs; unsupported signals stay omitted. Train contributors remain train, not subte.
- Fallback provenance now contains only criteria and evidence refs represented in rendered text. Geographic trade-offs render the concrete fact, and unchanged price snapshots do not add hidden price evidence.
- Frozen listing and observation snapshots require an exact listing identity match. Listing snapshots now persist `listing_id`; mismatching or identity-less snapshots are omitted from narrative context.
- Expanded human-facing labels for all currently supported narrative criteria and reused the shared label map from the scoring service.
- No database model, migration, scoring ranking/filtering, or LLM decision behavior was changed.

## TDD evidence

Initial focused suite before the new regressions: `33 passed`.

RED cycle for managed grounding, polarity, snapshot observation identity, and single-run resolution:

```text
pytest ... -q
7 selected tests: 2 passed, 5 failed
```

The failures were the expected missing behaviors: empty evidence accepted, negative nightlife placement, incomplete labels, foreign observation snapshot accepted, and duplicate latest-run resolution.

GREEN:

```text
pytest ... -q
7 passed
```

Additional RED/GREEN cycles:

- Geographic trade-off fact rendering: `1 failed` on the pre-fix implementation, then `32 passed` across the focused narrative/writer/service/endpoint contract set.
- Frozen listing identity: `1 failed` while the identity check was absent, then `2 passed` after adding the snapshot identity field and validation.
- Fallback provenance coverage passed with an explicit four-fact case proving the fourth, unrendered fact/ref is excluded.

## Verification

- Focused narrative/contracts suite: `47 passed, 11 warnings`.
- Relevant backend scoring/infrastructure/contracts suite: `126 passed, 11 warnings`.
- Web suite: `31 test files, 80 tests passed`.
- Web TypeScript typecheck: passed (`tsc --noEmit`, exit code 0).
- Ruff on all changed source and fixture files: passed.
- `git diff --check`: passed.
- Targeted strict mypy invocation: no errors in the changed narrative runtime modules or changed test fixtures. The command still reports 8 existing errors in unrelated files (`preferences/service.py`, `agent/graph.py`, and `api/dependencies.py`).
- Full `mypy src tests`: baseline remains failing with `195 errors in 36 files`; these are outside this task and were not broadened with ignores.

The FastAPI/HTTPX test client emitted the existing deprecation warnings noted above; they did not fail the tests.

## Files changed

- `src/umbral/api/routers/explanations.py`
- `src/umbral/application/scoring/contracts.py`
- `src/umbral/application/scoring/engine.py`
- `src/umbral/application/scoring/narrative.py`
- `src/umbral/application/scoring/service.py`
- `src/umbral/infrastructure/scoring/narrative.py`
- `tests/contract/test_explanation_endpoints.py`
- `tests/unit/application/scoring/test_narrative.py`
- `tests/unit/application/scoring/test_narrative_service.py`
- `tests/unit/infrastructure/scoring/test_narrative_writer.py`

## Commit

`f2e77956833502b1b36a715bb88f716f9b8cf6aa` — `feat: harden grounded match narratives`

## Limitations / concerns

- The full repository mypy baseline remains red as documented above. No full repository test suite claim is made; only the relevant backend and web suites were run.
- Test output retains 11 existing FastAPI/HTTPX deprecation warnings.
- Changes were not published or merged, and no migration/model-data change was created.
