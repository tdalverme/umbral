# Hardening task 1 — grounded narrative integrity

## Status

Complete after the independent-review and whole-branch correction rounds. Implemented on
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
- Final review correction: managed copy authorization is scoped to packets whose evidence refs and criteria are actually submitted in that response; descriptors from other context packets are no longer lexically authorized.
- Whole-branch correction: managed text now has a typed internal claim plan and deterministic sentence renderer, rejecting negations, contradictory placement, inverted price transitions, and declared refs that are not rendered.
- Whole-branch correction: geographic facts retain observed value/unit and signal direction; zero counts are omitted, distant signals become trade-offs instead of matches, and v2 contributor categories use the published contract identities.
- Whole-branch correction: negative non-geographic matches preserve their observed direction (`poca luz natural`), deterministic explanation labels cover supported concepts, UI caveats stay neutral when direction/cause is absent, and repeated selection preserves the loaded narrative.
- Whole-branch correction: fixed the introduced radar-service E501 and typed the two scoring test helpers without broad ignores.
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

## Independent-review correction rounds

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

The residual provenance-bypass RED test then failed as expected (`1 failed`):
`Encaja por la buena conectividad y la superficie.` was accepted while only the
transport criterion/ref was submitted. After scoping closed-world authorization
to submitted packet refs and criteria, the new test passed (`1 passed`). The
updated focused and relevant backend suites passed with `52 passed, 11 warnings`
and `131 passed, 11 warnings` respectively.

### Correction-round verification

- Web suite: `31 test files, 80 tests passed`.
- Web TypeScript typecheck: passed (`tsc --noEmit`, exit code 0).
- Ruff on all changed source and fixture files: passed.
- `git diff --check`: passed.
- Targeted strict mypy over the six changed source/fixture files: passed with no errors. The broader baseline invocation still reports 8 unrelated errors (`preferences/service.py`, `agent/graph.py`, and `api/dependencies.py`), and full `mypy src tests` remains at its documented 195-error baseline.
- Placement favorable/desfavorable, exact fallback provenance, and the managed happy path remain covered by the writer tests.
- No scoring/ranking/filter/activation/notification, model, migration, or web source changes were introduced.

Correction-round implementation commit: `99134da` — `fix: close narrative grounding review gaps`.
Residual correction implementation commit: `205b90c` — `fix: scope narrative copy to submitted packets`.
Whole-branch correction implementation commit: `e9004c2` — `fix: harden narrative semantics and geographic context`.
The report update is committed separately after this implementation commit.

## Whole-branch correction round

### TDD evidence

- Managed grounding RED: 5 regressions failed before the typed claim renderer (negated match, contradictory descriptor, mixed placement, inverted price transition, and unused declared price ref); writer GREEN: `23 passed`.
- Geographic/polarity RED: 4 regressions failed before measurement-aware classification and negative-direction projection; GREEN: `4 passed`.
- UI regressions cover neutral caveats and repeated same-identity selection; focused web result: `5 passed`.

### Verification

- Relevant backend scoring/infrastructure/urban/contracts suite: `179 passed, 11 warnings`.
- Adjacent backend radar/matching/notifications/criteria/voice groups: `185 passed`.
- Web suite: `32 test files, 83 tests passed`.
- Web TypeScript typecheck: passed.
- Targeted strict mypy over 10 changed source/test files: passed with no errors. The broader repository baseline remains documented separately and was not broadened with ignores.
- Ruff on changed Python paths reports only 7 pre-existing E501s in `src/umbral/application/radar/service.py`; the introduced line was fixed and no new Ruff error remains in the other changed files.
- `git diff --check`: passed.
- No scoring formula, ranking, hard-filter, activation, notification, database model, migration, or LLM decision behavior changed.

## Final whole-branch review correction round

### TDD evidence

- The real v2 UrbanSignalCalculator → scoring → explanation → narrative context → deterministic fallback → managed writer path reproduced the three geographic failures before implementation: zero daily services, unsupported nightlife presence, and reversed road-noise polarity. The contract-shaped luminosidad/estado_general enum path also reproduced the favorable copy inversion.
- GREEN end-to-end regressions: `5 passed`, covering zero/unsupported geographic facts, positive and negative road-noise polarity, and positive/negative contract enum values. The existing narrative and writer tests remained green: `47 passed` in the focused slice.
- The full listing-detail missing-data copy now shares the neutral `unknownCopy` helper with the opportunity sheet; the helper regression passed as part of the web suite.

### Correction

- Active urban observations without a concrete or proxy-safe geographic fact no longer authorize a favorable generic reason. They are omitted from match packets, so neither deterministic fallback nor the managed writer can claim nearby presence from a zero/unsupported signal.
- Geographic placement now derives from the normalized signal score, then applies the user polarity once. The v2 road-noise contract therefore renders far roads as a match and near roads as a tradeoff for an avoid preference, with the inverse placement covered for positive polarity.
- Contract-shaped enum values for `luminosidad` and `estado_general` now project their observed direction (`baja`, `malo`, `alta`, `bueno`, etc.) into the packet before narrative rendering.
- Full listing detail no longer attributes every missing datum to the source notice; it uses the same neutral uncertainty copy as the sheet.

### Verification

- Relevant backend scoring/infrastructure/urban/contracts suite: `184 passed, 11 warnings`.
- Adjacent backend radar/matching/notifications/criteria/voice groups: `185 passed`.
- Web suite: `33 test files, 84 tests passed`.
- Web TypeScript typecheck: passed (`tsc --noEmit`, exit code 0).
- Ruff on the Python files changed in this correction: passed. Targeted mypy on those three Python files: passed with no issues.
- `git diff --check`: passed. The branch-wide known baseline remains: 7 unchanged `E501` diagnostics in `src/umbral/application/radar/service.py`; they were not introduced by this round.
- No scoring formula, ranking, hard-filter, activation, notification, database model, migration, or LLM decision behavior changed.
