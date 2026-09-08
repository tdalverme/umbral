# Final re-review — hardening task 1: grounded narrative integrity

## Spec: PASS

## Quality: PASS

## Strengths

- Packet-scoped closed-world validation now derives authorized copy tokens only from packets whose criterion and evidence refs are both present in the submitted `used_criteria`/`used_evidence_refs` (`src/umbral/infrastructure/scoring/narrative.py:343-396`). A direct probe returned `authorized_unlisted=False` for the formerly accepted extra `superficie` descriptor, while the happy managed response returned `happy_managed=True`.
- Unknown additional copy is rejected (`src/umbral/infrastructure/scoring/narrative.py:244-250`, `343-396`); the `vista al río` probe returned `unknown_extra=False`.
- Placement and polarity are enforced for packet descriptors and geographic facts (`src/umbral/infrastructure/scoring/narrative.py:252-283`, `299-340`). Direct probes returned `negative_as_match=False` and `positive_as_tradeoff=False`.
- Identity-less and mismatched observation snapshots are omitted through required, exact `listing_id` validation (`src/umbral/application/scoring/service.py:614-623`); the identity-less probe returned `identityless_count=0`. Listing snapshots use the same exact identity check (`src/umbral/application/scoring/service.py:325-330`, `599-602`).
- The supported narrative concept set has human labels with no `"esta prioridad"` placeholders (`src/umbral/application/scoring/narrative.py:27-64`, `611-614`; probe returned `placeholder_labels=[]`).
- The selected explanation endpoint resolves an omitted run once and reuses it for both views (`src/umbral/api/routers/explanations.py:249-266`).
- Geographic identity remains bounded: train/subte terms are rendered distinctly (`src/umbral/application/scoring/narrative.py:469-479`, `496-515`), unsupported signals are omitted (`src/umbral/application/scoring/narrative.py:66-75`), and fallback provenance is limited to rendered facts (`src/umbral/application/scoring/narrative.py:157-195`).
- The scoring engine change only adds `listing_id` to the frozen narrative listing snapshot (`src/umbral/application/scoring/engine.py:273-283`). No scoring formula, ranking, hard-filter, activation, notification, model, migration, or database-model change was found.

## Issues

### Blocker

None identified.

### Critical

None identified.

### Major

None identified.

### Minor

None identified.

## Tests/commands executed and result

- `PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest tests/unit/application/scoring/test_narrative.py tests/unit/application/scoring/test_narrative_service.py tests/unit/infrastructure/scoring/test_narrative_writer.py tests/contract/test_explanation_endpoints.py -q` — **48 passed, 11 warnings**.
- `PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest tests/unit/application/scoring tests/unit/infrastructure/scoring tests/contract/test_explanation_endpoints.py -q` — **123 passed, 11 warnings**.
- Targeted regression selection covering packet provenance, managed happy path, placement, run resolution, fallback provenance, identity snapshots, train/subte, and unsupported signals — **9 passed, 39 deselected, 2 warnings**.
- Direct probes — authorized-unlisted descriptor **False**; happy managed **True**; unknown extra claim **False**; negative-as-match **False**; positive-as-tradeoff **False**; identity-less rehydration **0**; placeholder labels **none**.
- Ruff on all changed source and fixture files — **passed**.
- `git diff e1f21b1..f5adc16 --check` — **passed**.
- Targeted mypy invocation — **8 errors**, all existing unrelated baseline errors in `src/umbral/application/preferences/service.py`, `src/umbral/agent/graph.py`, and `src/umbral/api/dependencies.py`; no errors were reported in the changed narrative source or fixtures.

## Limitations

The full repository test suite was not claimed; verification is limited to the focused/relevant backend suites and targeted probes. Mypy remains red only on unrelated baseline files, and the test runs retain the existing FastAPI/HTTPX deprecation warnings.

No issues remain in the scoped final review.

## Whole-branch correction follow-up

The subsequent whole-branch review findings are also closed by `e9004c2`:
typed deterministic managed claims, measurement-aware geographic direction,
negative non-geographic fallback facts, v2 contributor coverage, local test
typing, neutral UI caveats, same-identity narrative preservation, and the
introduced radar-service lint line.

Fresh results for that round were `179 passed, 11 warnings` in the relevant
backend suite, `185 passed` in adjacent backend groups, `83 passed` web tests,
passing web typecheck, and no errors in targeted strict mypy over the changed
source/tests. Ruff retains only seven pre-existing E501s in the radar service;
`git diff --check` passes. No full repository pytest/mypy claim is made.
