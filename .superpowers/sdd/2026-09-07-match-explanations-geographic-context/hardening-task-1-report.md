# Hardening task 1 — grounded narrative integrity

## Status

Complete after the independent-review correction round. Implemented on
`feat/match-explanations-geographic-context` from base `e1f21b1`.

## Changes

- Managed narrative output now requires non-empty evidence and validates the claim against the same structured packet fact, active criterion, and submitted evidence reference. Invented price/amenity claims, empty refs, unrelated refs, raw keys, and unsafe copy fall back deterministically.
- Selected explanation requests resolve an omitted `run_id` once and reuse that UUID for the breakdown and optional narrative.
- Geographic facts retain their signal identity and are classified using criterion polarity. Conflicting avoid-style signals become trade-offs; unsupported signals stay omitted. Train contributors remain train, not subte.
- Fallback provenance now contains only criteria and evidence refs represented in rendered text. Geographic trade-offs render the concrete fact, and unchanged price snapshots do not add hidden price evidence.
- Frozen listing and observation snapshots require an exact listing identity match. Listing snapshots now persist `listing_id`; mismatching or identity-less snapshots are omitted from narrative context.
- Expanded human-facing labels for all currently supported narrative criteria and reused the shared label map from the scoring service.
- Review correction: managed claims now preserve packet placement (`match`, `tradeoff`, or `unknown`) and geographic polarity; a favorable fact cannot be presented as a concession and an unfavorable fact cannot be presented after `Encaja por`.
- Review correction: managed copy is closed-world against packet descriptors, authorized price-change values, and a small reviewed voice vocabulary. Additional factual phrases such as `vista al río` fall back without a claim-specific regex.
- Review correction: observation snapshots must contain an explicit string `listing_id`; missing and mismatched identities are omitted.
- Review correction: labels now cover v2 contract concepts including `piso`, `tipo_cocina`, `moderno`, `dormitorios`, `banos`, and `barrio_seguro`.
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

First-round commit: `e83dcaf07657afd64a39bc5a9a6fa84fd0be2904` — `feat: harden grounded match narratives`

## Limitations / concerns

- The full repository mypy baseline remains red as documented above. No full repository test suite claim is made; only the relevant backend and web suites were run.
- Test output retains 11 existing FastAPI/HTTPX deprecation warnings.
- Changes were not published or merged, and no migration/model-data change was created.

## Independent-review correction round

The review probe confirmed four gaps in the first commit: geographic placement could be reversed with valid refs, an untracked claim could follow a valid claim, an identity-less observation was treated as belonging to the requested listing, and six v2 concepts still used `esta prioridad`.

### TDD cycle

RED command:

```text
pytest tests/...four new regressions... -q
4 failed, 1 passed
```

The failures were the expected placement, closed-world, identity-less snapshot, and label coverage failures.

GREEN command:

```text
pytest tests/...four new regressions plus managed happy path... -q
6 passed
```

The full focused suite then passed with `51 passed, 11 warnings`, and the relevant backend scoring/infrastructure/contracts suite passed with `130 passed, 11 warnings`.

### Correction-round verification

- Web suite: `31 test files, 80 tests passed`.
- Web TypeScript typecheck: passed (`tsc --noEmit`, exit code 0).
- Ruff on all changed source and fixture files: passed.
- `git diff --check`: passed.
- Targeted strict mypy: 8 errors remain, all in unrelated baseline files (`preferences/service.py`, `agent/graph.py`, and `api/dependencies.py`); no errors in changed narrative runtime or fixtures.
- No scoring/ranking/filter/activation/notification, model, migration, or web source changes were introduced.

Correction-round implementation commit: `99134da` — `fix: close narrative grounding review gaps`.
Report commit: recorded in the final commit that adds this correction-round evidence.
