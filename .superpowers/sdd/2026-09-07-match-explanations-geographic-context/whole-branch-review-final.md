# Whole-branch final review

- **Spec: PASS**
- **Quality: PASS**
- Branch: `feat/match-explanations-geographic-context`
- HEAD reviewed: `c3da7c23ccfdacc830d5ddb7e1231d215d37bb91`
- Base / merge-base with main: `72ebf51af46d30b0fd17a8e268472b9597cbcd0c`
- Worktree: `D:\Tomi\dev\umbral\.worktrees\match-explanations-geographic-context`
- Date: 2026-09-08.
- Independent review, no subagents and no implementation changes. Previous reports were not used as evidence of correctness.

## Sources and scope

Read root AGENTS.md and PRODUCT.md, current worktree PRODUCT.md, the hardening brief, the supplied whole-branch diff package, current source and tests. The brief and diff do **not** exist at the requested root paths: the corresponding files were located and read under this worktree's `.superpowers/sdd/2026-09-07-match-explanations-geographic-context/`. Also read the original task 1–3 briefs to distinguish intended activation/weight normalization from regressions.

All source references below are relative to this exact worktree, with one-based HEAD line numbers.

## Strengths

- Managed validation now compares the entire output to packet-derived canonical sentences (`src/umbral/infrastructure/scoring/narrative.py:192`). Negation, appended contradiction, mixed placement and reversed price examples fall back. The existing valid two-claim example remains managed.
- Declared criteria and refs must equal the rendered claim sets (`src/umbral/infrastructure/scoring/narrative.py:320`). No global vocabulary authorization path remains. Existing tests exercise empty refs, unrelated refs, extra refs, invented amenities and facts not in the submitted packet.
- Listing identity is checked before using its snapshot; observation rehydration requires and checks listing identity (`src/umbral/application/scoring/service.py:331`, `:599`, `:605`). Tests cover mismatched listings/observations and identity-less observations.
- The endpoint resolves the latest run once and passes the resolved ID to both views (`src/umbral/api/routers/explanations.py:248`). The contract probe verifies exactly one resolution.
- Active-criterion filtering is shared by scoring and explanations. The original task explicitly calls for active-weight renormalization; this branch is not score-identical to the base by design. Targeted deterministic ranking, hard-filter, activation and notification tests pass.
- The narrative writer remains presentation-only, invoked on the selected explanation path, not the list/scoring/notification path. No DB model or migration changes appear in the whole-branch diff.
- Web tests cover human-facing copy, the selected-explanation BFF flag, neutral unknown copy in the sheet and same-listing/same-run reset behavior.
- No introduced Ruff, targeted mypy or ESLint diagnostics were found after comparison against the base. Existing failures are detailed below.

## Issues

### Blocker / Critical

None found.

### Major 1 — Zero/unsupported geographic facts leave a favorable generic reason alive

**Location:** `src/umbral/application/scoring/narrative.py:303`–`:328`; `:479`–`:484`; nightlife distance has no rendering branch in `_phrase` (`:561`–`:628`).

The context initially includes every material evaluation whose state is `match`. It removes the reason only if geographic conversion produced an explicitly unfavorable fact. Zero-count contributors are skipped; unsupported distance phrases return no fact. In both cases the original favorable label survives.

This matters because a present soft urban signal with score zero is still `state="match"` in the existing evaluator (`src/umbral/application/scoring/evaluators.py:221`). A match state alone does not establish nearby presence.

**Executed reproduction:** use the real v2 UrbanSignalCalculator, score_candidates, build_explanation, build_narrative_context and deterministic_narrative (script below).

- Positive `proximidad_compras`: all supermarket/pharmacy/convenience/health count_600m buckets contain only a distance of 2000 m. Calculator contributors explicitly report four counts of zero; evaluation is `("match", 0.0)`; geography is empty.
- Actual output: **“Encaja por servicios cotidianos cerca.”**
- Positive `vida_nocturna`: count_300m has no in-radius places and nearest_m is 2000 m. Contributors report zero and 2000 m; evaluation is `("match", 0.0)`; geography is empty.
- Actual output: **“Encaja por actividad nocturna.”**
- Submitting those exact texts and their provenance to ManagedExplanationNarrativeWriter returns **source="managed"**.

**Impact:** unsupported proximity/presence claims escape both fallback and managed output. The canonical validator cannot repair a false descriptor already authorized by the packet. This violates requested check 3 and the hardening brief's concrete-fact/proxy-safe requirements.

**Required correction:** distinguish “no usable fact” from a favorable fact when building geographic reasons. Omit or neutrally qualify unsupported measurements and preserve zero/distance semantics before authorizing a match sentence. Add end-to-end packet tests; the current zero test only asserts that geographic_facts returns an empty tuple.

### Major 2 — Avoiding road noise reverses the distance placement

**Location:** `src/umbral/application/scoring/narrative.py:530`–`:531`, combined with `:436`.

For road_noise, signal_positive currently means distance >=120 m, i.e. *less* exposure. The common polarity handler then inverts that for a negative/avoid preference. The actual road_noise contract assigns higher values to nearer roads (`contracts/urban/v2/urban-contract-v2.json:141`), so this double interpretation reverses what the user asked for.

**Executed reproduction**, real v2 calculator through scoring and narrative, `ruido_transito`, polarity negative:

- Both major_road and highway at 500 m: observed score 0, preference evaluation score 1.0. The favorable “alejada de los principales corredores” fact is removed from matches and emitted as a mismatch/tradeoff.
- Actual output: **“Encaja con parte de lo que buscás. Alejada de los principales corredores es un punto para revisar.”**
- Both roads at 40 m: observed score 1.0, preference evaluation score 0.0. The near-road fact is classified favorable.
- Actual output: **“Encaja por menor exposición y con una avenida principal relativamente cerca.”**

**Impact:** the person avoiding traffic exposure sees the undesired condition as a reason to match, and the desired condition as a tradeoff. This violates requested check 3 and the direction-preservation requirement.

**Required correction:** define road signal polarity consistently with the contract before applying the preference's polarity. Test both near/far values and positive/negative preferences through context construction, not only the standalone phrase formatter.

### Major 3 — Non-geographic negative polarity is only patched for a non-contract luminosidad value

**Location:** `src/umbral/application/scoring/narrative.py:650`–`:665`, especially `:659`–`:664`; positive defaults at `:35`–`:36`.

The only direction-aware non-geographic descriptor handles luminosidad when observation.value is numeric. The actual extraction contracts encode luminosidad as `"baja" | "media" | "alta"`, and estado_general as `"malo" | "regular" | "bueno" | "muy_bueno"` (`contracts/criteria/v3/extraction-v3.json:29`, `:39`; also present in v1).

**Executed reproduction:**

- luminosidad, polarity negative, value `"baja"`, observation score 0.1: real scorer returns match/0.9, but the packet has label “buena luz natural” and no fact.
- Actual output: **“Encaja por buena luz natural.”**, accepted as **managed**.
- estado_general, polarity negative, value `"malo"`, score 0.1: real scorer returns match/0.9.
- Actual output: **“Encaja por buen estado general.”**, accepted as **managed**.
- Control: numeric luminosidad value 0.1 produces “Encaja por poca luz natural.” and remains managed. This explains why the current regression test passes while the contract-shaped value fails.

**Impact:** the explanation states the opposite of the observed property. Negative estado_general is explicitly supported by the preference vocabulary (`contracts/criteria/v1/preferences-vocabulary-v1.json:30`). This violates requested check 4; the gap is not limited to a hypothetical unknown concept.

**Required correction:** build descriptors from the supported observation value/direction contract across relevant non-geographic concepts. Use real enum fixtures and cover both fallback and managed acceptance.

### Minor 1 — Full listing detail still invents the cause of unknown data

**Location:** `apps/web/src/app/(protected)/listings/[id]/page.tsx:39`.

The sheet now uses neutral wording, but the full listing detail renders every missing_data entry as “No puedo confirmar …: el aviso no lo informa.”

**Reproduction by direct source inspection:** return an explanation with `missing_data: ["vida_nocturna"]` because the urban snapshot is unavailable, then open the listing detail in that radar/run context. Line 39 renders **“No puedo confirmar actividad nocturna: el aviso no lo informa.”** The API's missing_data key does not establish that the listing omitted information; a missing urban snapshot is a different cause.

**Impact:** the two detail surfaces disagree, and one attributes uncertainty to unsupported source content. Violates requested check 6 and PRODUCT.md's honest uncertainty rule.

**Required correction:** reuse the sheet's neutral unknown wording unless an explicit cause is available. Add coverage for the full listing page. This reproduction is static; no browser assertion was executed for this page.

## Requested checks

| Check | Result and evidence |
| --- | --- |
| 1. Negations/contradictions/placement/inverted price; managed happy path | PASS for writer boundary: existing focused tests executed successfully, including valid managed output. |
| 2. Every ref represented; packet-only claims | PASS for structural authorization in the writer. Packet semantic truth FAILS for Major 1 and 3; exact-copy validation does not establish source truth. |
| 3. Zero/distances/polarity/train/subte/v2 | FAIL: Major 1 and 2. Train/subte identity, unrelated/unsupported contributors and green_space/supermarket/restaurant v2 examples pass their current tests. |
| 4. Negative non-geographic direction | FAIL: Major 3 with contract-shaped observations. |
| 5. Snapshot identity / single run | PASS in inspected implementation and executed unit/contract tests. Identity-less listing snapshots also fail the explicit equality guard; no dedicated identity-less-listing test was added. |
| 6. Human labels / neutral unknown / same identity | PARTIAL: sheet tests and reset helper pass; Minor 1 remains. Same-identity behavior was tested by the existing helper suite and inspected in RadarShell, not with a new full-shell browser test. |
| 7. Scoring/ranking/filters/activation/notifications/DB/LLM | No additional regression found in focused suites and diff inspection. Active weighting intentionally changes per original brief. No DB models/migrations; writer does not make product decisions. Broader suite was not completed. |
| 8. Typing / lint | No new diagnostics found. Full lint/changed-file mypy are not globally green due to verified baseline failures. |

## Tests / commands and results

Run from this worktree unless stated otherwise. Python executable: `D:\Tomi\dev\umbral\.venv\Scripts\python.exe`. Python commands set `$env:PYTHONPATH='src'`; pytest used `-p no:cacheprovider`.

1. `python -m pytest -p no:cacheprovider tests/unit/application/scoring tests/unit/infrastructure/scoring tests/unit/application/urban tests/contract/test_explanation_endpoints.py tests/contract/test_explanation_narrative.py tests/contract/test_explanations.py -q`
   - **165 passed**, 11 deprecation warnings, 21.45 s.
   - Warnings: Starlette/httpx testclient and per-request cookies.

2. `python -m pytest -p no:cacheprovider tests/unit/application/radar tests/unit/application/notifications tests/unit/application/criteria tests/contract/test_evaluators.py tests/contract/test_scoring_policy.py tests/contract/test_matching_regression.py tests/contract/test_matching_golden.py tests/contract/test_matching_fidelity.py tests/contract/test_notifications_policy.py tests/contract/test_notifications_planner_golden.py tests/contract/test_notification_events.py -q`
   - **186 passed**, 1.89 s.

3. In `apps/web`: `npm test`
   - **32 test files / 83 tests passed**, 42.89 s.
   - Initial attempt `npm test -- --reporter=dot` was rejected by the installed npm as an unknown CLI flag; reran without it.

4. In `apps/web`: `npm run typecheck`
   - **PASS**, exit 0, no TypeScript diagnostics.

5. Ruff on all 27 changed Python files:
   - `$changedPython = @(git diff --name-only 72ebf51 HEAD -- '*.py'); python -m ruff check --no-cache @changedPython`
   - **7 E501 errors**, all in `src/umbral/application/radar/service.py`: 466, 467, 623, 630, 693, 696, 724.
   - Re-ran Ruff against `git show 72ebf51:src/umbral/application/radar/service.py` via stdin with the real stdin filename: **the same 7 E501 errors at the same lines**.
   - All remaining changed Python files: **All checks passed**.

6. Strict targeted mypy on all 27 changed Python files:
   - `python -m mypy --cache-dir=nul @changedPython`
   - **1 assignment error** in `tests/unit/application/scoring/test_run_publish.py:291`, assigning conflicting_publish to FakeRunRepository.publish; its method-assign ignore does not cover assignment.
   - Verified the base file with mypy's build API using the base source text in memory and the same project options: **same assignment error at base line 293**. This branch only removes two unrelated expected criterion names from that test file.
   - Remaining 26 changed Python files: **Success: no issues found in 26 source files**.
   - A preliminary `mypy -c` baseline attempt was rejected because the project also configures files; the in-memory build above is the successful baseline diagnostic comparison.

7. In `apps/web`: `npm run lint`
   - **7 errors, 14 warnings**, exit 1. Not a global PASS.
   - Errors in login/page.tsx, chat/chat-panel.tsx, chat/message-list.tsx, radar/chat/radar-chat-panel.tsx, opportunity-detail-sheet.tsx and radar-shell.tsx (two).
   - Used ESLint.lintText on HEAD and base source obtained with git show, under current configuration, for all 13 changed TS/TSX files. Same rules/diagnostics remain in changed files; **zero unmatched/new diagnostics**. Radar page has one fewer unused warning.
   - The error-bearing files outside the changed set are unchanged in the branch.

8. `git diff --check 72ebf51 HEAD`
   - **PASS**.
   - No paths changed under DB models/migrations.

9. Expanded exploratory run:
   - `python -m pytest -p no:cacheprovider tests/unit/application/radar tests/unit/application/notifications tests/unit/application/criteria tests/unit/application/scoring tests/unit/infrastructure/scoring tests/unit/application/urban tests/contract -q`
   - **Interrupted, not PASS**. Partial output showed a failure and multiple setup errors; no final summary/tracebacks were produced before interruption. Those errors are not assigned to this branch or to Docker without evidence.
   - Its generated-client contract test regenerated 17 tracked web-client files. It checks git status, and these files showed modified status even though normalized git diff had no content changes. Restored those files from exact HEAD using checkout filters; final tracked status returned clean. The published OpenAPI/client/config inputs are unchanged by this branch, but this interrupted run is not used as a conformance PASS.

10. Independent probes below:
    - Executed against HEAD, real calculator/scorer/context/writer and repository fake gateway.
    - Reproduced all three Major findings. No implementation/test files were added for the probes.

## Reproduction script for Major findings

Execute from the worktree with PYTHONPATH=src using the Python executable above. The script uses the existing fake gateway and fixture builders; it does not contact a provider or modify source files. Observations use explicit test scores; geographic values/contributors come from the real v2 calculator.

```python
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from tests.support.radar import build_listing, build_profile
from tests.support.scoring import build_compilation, build_criterion, build_observation, MATCHER_TYPES, SEED, TEMPLATES
from tests.unit.infrastructure.scoring.test_narrative_writer import ScriptedGateway, _writer
from umbral.application.scoring.engine import score_candidates
from umbral.application.scoring.policy import parse_policy_document
from umbral.application.scoring.explanations import build_explanation
from umbral.application.scoring.narrative import build_narrative_context, deterministic_narrative, narrative_label
from umbral.application.urban.calculator import UrbanSignalCalculator
from umbral.application.urban.contract import load_urban_contract

policy = parse_policy_document(SEED, MATCHER_TYPES)
calc = UrbanSignalCalculator(load_urban_contract(Path("contracts/urban/v2/urban-contract-v2.json")))

def probe(key, polarity, *, score=None, value=None, signal=None, poi=None, linear=None):
    profile, listing, run_id, version_id = build_profile(), build_listing(), uuid4(), uuid4()
    matcher = "signal_score" if signal else "semantic_feature"
    evidence = {}
    if signal:
        measured = calc.calculate(poi_distances=poi, linear_distances=linear).for_signal(signal)
        score = value = measured.value
        evidence = {"signal_ref": signal, "contributors": list(measured.contributors)}
    observation = replace(build_observation(listing_id=listing.listing_id, concept_key=key, value=value, score=score),
        matcher_type=matcher, source="urban" if signal else "model", evidence=evidence)
    observations = {key: observation}
    compilation = build_compilation(profile_id=profile.profile_id, profile_version_id=version_id,
        criteria=(build_criterion(key, matcher_type=matcher, params={"polarity":polarity}, weight=1),))
    candidate = score_candidates(profile=profile, compilation=compilation, candidates=(listing,),
        observations={listing.listing_id:observations}, policy=policy, run_id=run_id,
        correlation_id=uuid4(), now=datetime.now(timezone.utc))[0]
    evaluation = next(e for e in candidate.evaluations if e.criterion_key == key)
    explanation = build_explanation(search_profile_id=profile.profile_id, run_id=run_id, listing_id=listing.listing_id,
        score=candidate.score, confidence=candidate.confidence, evaluations=(evaluation,), policy=policy,
        templates=TEMPLATES, satisfied_filters=(), profile_version_id=version_id)
    context = build_narrative_context(explanation=explanation, listing=candidate.narrative_listing,
        active_criteria={key:{"label":narrative_label(key),"polarity":polarity}}, observations=observations)
    result = deterministic_narrative(context)
    gateway = ScriptedGateway()
    gateway.output = {"text":result.text,"used_criteria":list(result.used_criteria),"used_evidence_refs":list(result.used_evidence_refs)}
    managed = _writer(gateway).write(context)
    print(key, polarity, "observed=", value, "evaluation=", (evaluation.state,evaluation.score))
    print("contributors=",evidence.get("contributors"),"geography=", [(g.value,g.favorable) for g in context.geography])
    print("reasons=",context.reasons, "tradeoffs=",context.tradeoffs)
    print("OUTPUT:",result.text,"MANAGED:",managed.source)
    return context

probe("estado_general","negative",score=0.1,value="malo")
probe("luminosidad","negative",score=0.1,value="baja")
probe("luminosidad","negative",score=0.1,value=0.1)
probe("vida_nocturna","positive",signal="nightlife_intensity",poi={"nightlife":{"count_300m":[2000.0],"nearest_m":[2000.0]}})
probe("proximidad_compras","positive",signal="daily_convenience",poi={k:{"count_600m":[2000.0]} for k in ["supermarket","pharmacy","convenience","health"]})
probe("ruido_transito","negative",signal="road_noise",linear={"major_road":{"nearest_m":[500.0]},"highway":{"nearest_m":[500.0]}})
probe("ruido_transito","negative",signal="road_noise",linear={"major_road":{"nearest_m":[40.0]},"highway":{"nearest_m":[40.0]}})
```

## Limitations

- No live managed-provider call, production database, deployed browser E2E or full build was run. Managed tests use a scripted provider boundary.
- Passing focused suites do not establish that the entire repository passes. The broader exploratory contract run was interrupted and has unclassified failures/setup errors.
- The geographic probes use the real urban calculator and scoring functions with controlled in-memory observations; they do not validate live PostGIS distance extraction or production normalization.
- Review introduces only this report as an intentional artifact. Test-generated client changes were restored; no commits, branch changes, implementation edits or subagents.
- Existing review reports were not treated as proof. These findings are based on current source and newly executed checks.

**Conclusion before correction round:** 3 Major and 1 Minor issues remained. No Blocker/Critical issue was found.

## Final correction round resolution

The four findings above were implemented in the same worktree with no subagents, publication, or merge:

- Major 1: the narrative context now removes an active urban match when the real v2 signal has no concrete/proxy-safe geographic fact. The end-to-end tests run UrbanSignalCalculator → score_candidates → build_explanation → build_narrative_context → deterministic_narrative and the managed writer for zero daily services and unsupported nightlife; neither emits a favorable presence claim.
- Major 2: geographic placement now uses the normalized contract signal score as the signal direction and applies user polarity once. Real v2 road-noise tests cover 500m/40m and both positive/negative preferences; avoiding noise makes the far-road fact a match and the near-road fact a tradeoff.
- Major 3: the packet projection now handles contract enum values for luminosidad and estado_general, preserving observed low/bad/high/good direction. End-to-end tests cover negative and positive values and the writer boundary.
- Minor 1: the full listing detail reuses the neutral `unknownCopy` helper used by the sheet; a helper regression guards against the unsupported “el aviso no lo informa” cause.

### Final correction verification

- Relevant backend scoring/infrastructure/urban/contracts: `184 passed, 11 warnings`.
- Adjacent backend radar/matching/notifications/criteria/voice groups: `185 passed`.
- Web: `33 test files, 84 tests passed`; typecheck passed.
- Ruff on the Python files changed in this round: passed. Targeted mypy on those files: passed.
- `git diff --check`: passed. The previously documented branch baseline remains: 7 unchanged Ruff `E501` diagnostics in `src/umbral/application/radar/service.py`.
- No scoring formula, ranking, hard-filter, activation, notification, database model, migration, or LLM decision behavior changed.

**Final conclusion:** the 3 Major and 1 Minor findings are resolved. The branch is ready for the requested handoff, subject to the existing documented baseline diagnostics and the review limitations above.
