# Whole-branch final re-review

- **Spec: PASS**
- **Quality: PASS**
- **HEAD before report commit:** `5da5e5f`
- **Correction commit:** `5da5e5f`
- **Base:** `72ebf51af46d30b0fd17a8e268472b9597cbcd0c`
- **Branch:** `feat/match-explanations-geographic-context`
- **Worktree:** `D:\Tomi\dev\umbral\.worktrees\match-explanations-geographic-context`
- **Date:** 2026-09-08.

Independent re-review, without subagents, code edits or brief edits. This report replaces the previous final report. Two Major content-integrity issues were identified in that re-review; no Blocker, Critical or Minor issue was identified.

## Scope and sources

Read the current AGENTS.md, PRODUCT.md, hardening brief, previous final review, updated implementation report and `review-72ebf51..f2136e7.diff`. Inspected the current code and tests, with detailed comparison of `c3da7c2..HEAD` against the previous whole-branch review. Reports were context, not proof of passing behavior.

File references below are relative to the exact worktree above, with one-based HEAD line numbers.

## Strengths

- Zero-count and unsupported active urban observations now remove the corresponding favorable generic reason, rather than merely disappearing from geography (`src/umbral/application/scoring/narrative.py:322`–`:341`). Independent probes explicitly submitted the old false sentences to the writer and confirmed rejection.
- Luminosidad and estado_general now use the actual extraction enums. Independent low/negative and high/positive probes preserve direction and remain managed (`src/umbral/application/scoring/narrative.py:669`–`:689`).
- The four homogeneous road-distance/polarity combinations now classify geography correctly: negative/far and positive/near are matches; negative/near and positive/far are tradeoffs. The remaining generic wording issue is reported separately below.
- Full listing detail and the opportunity sheet now share neutral unknownCopy (`apps/web/src/lib/radar/criterion-labels.ts:46`, `apps/web/src/app/(protected)/listings/[id]/page.tsx:39`, `apps/web/src/components/radar/opportunities/opportunity-detail-sheet.tsx:152`).
- Writer canonical sentence equality and exact rendered criterion/ref set checks remain unchanged and pass the executed adversarial tests (`src/umbral/infrastructure/scoring/narrative.py:192`, `:320`–`:326`). Negation, appended contradiction, mixed placement, reversed price, invented facts, empty/unrelated refs and unused declared refs are rejected; authorized happy paths remain managed.
- Frozen snapshot identity checks and single latest-run resolution remain intact; their tests were rerun (`src/umbral/application/scoring/service.py:331`, `:599`, `:605`; `src/umbral/api/routers/explanations.py:248`).
- The selected narrative remains presentation-only. No model decision path was added to scoring, ranking, hard filtering, activation or notifications. There are no DB-model/migration changes in the whole branch.
- **356 backend tests and 84 web tests passed**, and TypeScript typecheck passed. Strict targeted typing and lint show no new diagnostics after fresh baseline comparison.

## Status of the four previous findings

| Previous finding | Current result |
| --- | --- |
| Zero/unsupported geographic facts leave favorable reasons and pass managed | **Closed for the reproduced cases.** Zero daily services, distant/zero nightlife and unsupported school_access produce no favorable reason/geography. Explicitly submitting each old favorable sentence returns deterministic_fallback. |
| Road-noise near/far polarity reversed | **Placement fixed; semantic closure incomplete.** All four geography placements pass, but positive/near still authorizes “menor exposición” through its generic reason. See Major 2. |
| Luminosidad/estado_general contractual enums invert direction | **Closed for the requested enums.** baja/negative -> “poca luz natural”; malo/negative -> “estado general deteriorado”; alta/positive and bueno/positive keep their favorable observations. All four independent probes remain managed. |
| Full listing detail invents “el aviso no lo informa” | **Closed.** It calls the same tested neutral helper as the sheet. No unsupported cause is appended at the call site. |

## Issues

### Blocker / Critical

None found.

### Major 1 — A favorable aggregate score promotes an unfavorable contributor into “Encaja por”

**Location:** `src/umbral/application/scoring/narrative.py:437`, `:528`–`:541`; contributor selection at `:473`.

The correction now determines each rendered geographic fact's direction using the **whole observation's score**. The rendered phrase still comes from the first supported individual contributor. Other contributors can raise the aggregate score above 0.5 even when the selected contributor is unfavorable. Thus a distant station borrows the favorable direction of unrelated transport measurements.

**Executed reproduction using the real v2 calculator, urban observation builder, scoring, explanation, packet and writer:**

```python
poi_distances = {
    "bus_stop": {"count_300m": [50, 60, 70]},
    "subway_station": {"nearest_m": [2000]},
    "train_station": {"nearest_m": [250]},
}
# active acceso_transporte, polarity positive
```

The v2 contract computes transit_access = **0.6**: 0.45 from buses, zero from the far subway, 0.15 from the nearby train. The formatter skips the bus count (no transit/places phrase), selects the subway distance, and classifies it favorable because 0.6 >= 0.5.

Observed output:

- Geography: `("con subte a una distancia mayor", favorable=True)`.
- Fallback: **“Encaja por buena conectividad y con subte a una distancia mayor.”**
- Explicit writer output **“Encaja por con subte a una distancia mayor.”**, with just the corresponding urban ref, is accepted as **source="managed"**.

**Impact:** a real unfavorable distance is advertised as a reason to fit a positive transport preference. This violates the requested distance/placement guard and the brief's concrete-fact requirement. It is not a malformed observation: every contributor and the aggregate score came from the current v2 calculator.

**Required correction:** retain contributor-specific factual direction when assigning placement, or choose/render a contributor that actually supports the favorable aggregate claim. The road-noise polarity correction must not make all geographic facts inherit a composite score's direction.

**Coverage gap:** the existing far-transit test now sets its observation value to 0.0; it does not test mixed favorable and unfavorable contributors. Add the mixed bus/subway/train case through final text and managed acceptance.

### Major 2 — Near-road positive preference still authorizes the opposite generic descriptor

**Location:** `src/umbral/application/scoring/narrative.py:56`, `:336`–`:341`, `:644`–`:654`.

The geographical fact has the correct positive/near placement after the fix, but its original generic reason survives alongside it. That reason uses the fixed label **“menor exposición”**, independent of the observed road-noise direction, and has no direction-aware fact descriptor. The writer can select this reason alone and present the opposite claim.

**Executed reproduction:**

- v2 major_road.nearest_m = 40 m; highway.nearest_m = 40 m.
- The real calculator returns road_noise **1.0**.
- Active ruido_transito with **positive** polarity.
- Geography correctly contains the favorable descriptor “con una avenida principal relativamente cerca”.
- Fallback nevertheless says **“Encaja por menor exposición y con una avenida principal relativamente cerca.”**
- Submitting **“Encaja por menor exposición.”**, criterio ruido_transito and the valid observation ref, is accepted as **source="managed"**.

**Impact:** correcting placement alone has not preserved the observed direction of the final narrative. High road exposure can still be stated as lower exposure, in both deterministic and managed presentation. Positive and negative polarity were explicitly part of the requested verification.

**Required correction:** suppress or replace direction-bearing generic labels when a geographic fact is available; ensure every authorized descriptor agrees with that observation's direction. Test the final fallback and canonical managed selection, not only context.geography/tradeoffs membership.

### Minor

None found in this re-review. The previous full-detail unknown wording issue is corrected.

## Other requested checks

| Area | Result |
| --- | --- |
| Writer negations/contradictions/placement/inverted price | Executed tests pass. No reopened structural bypass found. |
| Packet-only claims; every declared ref represented | Structural checks pass. The two Major findings are semantically incorrect facts already authorized by the packet, not vocabulary/ref-membership bypasses. |
| Zero/unsupported facts | Original cases plus unsupported school probe pass. |
| Geographic distances / polarity | FAIL overall: mixed contributors and generic road wording above. Homogeneous four-way road placements now pass. |
| v2 categories; train/subte identity | Existing tests rerun and pass for green_space, supermarket, restaurant and train identity; the mixed transport probe exposes the separate placement defect. |
| Non-geographic enums | Requested luminosidad/estado_general cases pass independent assertions, including source="managed". |
| Snapshots and one run | Existing unit/contract tests rerun and pass; guards and endpoint flow unchanged in the correction. |
| Human labels / unknown UI / same identity | Existing label, sheet, BFF, neutral helper and same-identity helper tests pass. Full-page helper call and RadarShell flow inspected; no new browser integration test was created. |
| Scoring / ranking / filters / activation / notifications | Targeted suites pass. These modules are unchanged by 6891c15; active-weight renormalization remains the earlier explicitly planned whole-branch behavior. |
| Models / migrations / model decisions | No DB model/migration changes; LLM remains presentation-only. |
| Type/lint regressions | None introduced in tested scope; verified baseline failures remain below. |

## Tests / commands and results

All Python commands ran from the worktree with `$env:PYTHONPATH='src'`, using `D:\Tomi\dev\umbral\.venv\Scripts\python.exe`.

### Backend

```text
python -B -m pytest -p no:cacheprovider
  tests/unit/application/scoring
  tests/unit/infrastructure/scoring
  tests/unit/application/urban
  tests/unit/application/radar
  tests/unit/application/notifications
  tests/unit/application/criteria
  tests/contract/test_explanation_endpoints.py
  tests/contract/test_explanation_narrative.py
  tests/contract/test_explanations.py
  tests/contract/test_evaluators.py
  tests/contract/test_scoring_policy.py
  tests/contract/test_matching_regression.py
  tests/contract/test_matching_golden.py
  tests/contract/test_matching_fidelity.py
  tests/contract/test_notifications_policy.py
  tests/contract/test_notifications_planner_golden.py
  tests/contract/test_notification_events.py
  -q
```

Run as one command: **356 passed, 11 warnings, 7.24 s**. Warnings are the Starlette/httpx testclient and per-request cookie deprecations.

### Web

From `apps/web`:

- `npm test`: **33 files / 84 tests passed**, 11.47 s.
- `npm run typecheck`: **PASS, exit 0**, no diagnostics. Also rerun independently of the lint command to verify the exit status.
- `npm run lint`: **7 errors, 14 warnings**, exit 1. Not a whole-project lint PASS.

Fresh ESLint.lintText comparison of base and HEAD, under the current config, across **14 changed TS/TSX files**: zero unmatched/new diagnostics. Existing changed-file diagnostics remain in opportunity-detail-sheet, radar-shell, floating-list and radar page; radar page has one fewer warning. Other error-bearing files are unchanged from base.

### Python lint and typing

Changed files selected by `git diff --name-only 72ebf51 HEAD -- '*.py'`:

- `python -m ruff check --no-cache @changedPython`: 7 E501s in `src/umbral/application/radar/service.py` at 466, 467, 623, 630, 693, 696, 724.
- Re-ran Ruff with the base radar/service.py source via stdin and real stdin filename: **exact same 7 E501s at the same lines**.
- Clean changed-file slice excluding that baseline file and the baseline mypy fixture: **All checks passed**.
- `python -m mypy --cache-dir=nul @changedPython`: one error across 28 files, `tests/unit/application/scoring/test_run_publish.py:291`, incompatible assignment to publish.
- Fresh mypy build with the **base source text in memory**, same project options: **the same assignment error at base line 293**. The differing lines are two removed unrelated expected criteria.
- Excluding that baseline fixture: **Success: no issues found in 27 source files**.
- No code/ignore edits were made to obtain these results.

### Independent probes

- Executed the full reproduction script below against HEAD; both false sentences return source="managed".
- Executed a four-case 40 m/500 m × positive/negative road matrix through real calculator and narrative: placements match the contract; positive/near text still fails as described.
- Executed three zero/unsupported cases, explicitly submitting their old false favorable statements with observation refs: **3/3 rejected**, empty favorable reasons/geography.
- Executed four real-enum cases: luminosidad baja/negative, alta/positive, estado_general malo/negative, bueno/positive: **4/4 preserve expected copy and remain managed**.

### Repository checks

- `git diff --check 72ebf51 HEAD`: **PASS**.
- No changed paths under DB models, alembic or migrations.
- HEAD stayed `f2136e7`. Before report replacement the worktree was clean.
- No generated-client or all-contract regeneration tests were run this time; they modify generated code and were unnecessary for this bounded re-review.

## Executed reproduction for remaining issues

Run from the worktree with PYTHONPATH=src and the Python executable above. Uses existing test builders/fake gateway and real production calculator/scorer/packet/writer; no provider call or file modification.

```python
from uuid import uuid4
from tests.unit.application.scoring.test_narrative_end_to_end import (
    _urban_observation, _narrative_for_observation, CONTRACT_PATH,
)
from tests.unit.infrastructure.scoring.test_narrative_writer import ScriptedGateway, _writer
from umbral.application.urban.calculator import UrbanSignalCalculator
from umbral.application.urban.contract import load_urban_contract

calc = UrbanSignalCalculator(load_urban_contract(CONTRACT_PATH))

# Major 1: low-quality subway access borrows the aggregate score of bus/train.
result = calc.calculate(poi_distances={
    "bus_stop": {"count_300m": [50, 60, 70]},
    "subway_station": {"nearest_m": [2000]},
    "train_station": {"nearest_m": [250]},
})
obs = _urban_observation(listing_id=uuid4(), concept_key="acceso_transporte",
                         signal_ref="transit_access", result=result)
context, fallback, _ = _narrative_for_observation(
    concept_key="acceso_transporte", polarity="positive", observation=obs)
print("transit score:", obs.score)
print("facts:", [(f.value, f.favorable) for f in context.geography])
print("fallback:", fallback.text)
gateway = ScriptedGateway()
gateway.output = {
    "text": "Encaja por con subte a una distancia mayor.",
    "used_criteria": ["acceso_transporte"],
    "used_evidence_refs": [context.geography[0].source_ref],
}
print("managed:", _writer(gateway).write(context))

# Major 2: correct geographic placement retains an opposite generic descriptor.
result = calc.calculate(linear_distances={
    "major_road": {"nearest_m": [40.0]},
    "highway": {"nearest_m": [40.0]},
})
obs = _urban_observation(listing_id=uuid4(), concept_key="ruido_transito",
                         signal_ref="road_noise", result=result)
context, fallback, _ = _narrative_for_observation(
    concept_key="ruido_transito", polarity="positive", observation=obs)
print("road score:", obs.score)
print("fallback:", fallback.text)
reason = context.reasons[0]
gateway.output = {
    "text": "Encaja por " + reason["label"] + ".",
    "used_criteria": ["ruido_transito"],
    "used_evidence_refs": list(reason["evidence_refs"]),
}
print("managed:", _writer(gateway).write(context))
```

## Limitations

- No live managed-provider evaluation, browser E2E, production PostGIS, full build or full repository suite. Passing focused tests does not imply those checks pass.
- Geographic probes use controlled valid distance buckets; they verify calculation through narrative output, not live distance ingestion or barrio normalization.
- Same-identity and neutral copy were verified with the existing web tests plus source call-site inspection, not a newly added full-shell/full-page browser test.
- Reports were read for context only. All test counts, baseline diagnostics and observed failures above were checked in this re-review.
- Only this report was intentionally replaced. No implementation/brief edits, commits or subagents.

**Final verdict before this correction round:** Spec FAIL and Quality FAIL. Two Major issues remained, both reproduced in managed output despite valid references. The previous zero/unsupported, contractual-enum and unknown-copy failures were fixed.

## Final correction round resolution

The two remaining findings were reproduced with RED tests and corrected in the same worktree, without subagents, publication or merge:

- Major 1: geographic placement now uses the selected contributor's own observed value and unit. In the v2 mixed bus/train/subte case, the selected subte at 2000m is classified as a tradeoff even though the aggregate `transit_access` score is `0.6`; the final fallback and managed boundary cannot promote that contributor to a favorable match.
- Major 2: when a concrete geographic fact exists for a criterion, its generic evaluation reason is removed from the narrative packet. The near-road positive case now ends with only the observed avenue fact; “menor exposición” cannot be submitted as a separately accepted managed claim.

### Final correction verification

- TDD RED: the new mixed-contributor and near-road final-text assertions failed before implementation (`2 failed`).
- TDD GREEN: focused narrative/end-to-end/writer suite `49 passed`.
- Relevant backend scoring/infrastructure/urban/contracts suite: `185 passed, 11 warnings`.
- Adjacent backend radar/matching/notifications/criteria/voice groups: `185 passed`.
- Web suite: `33 test files, 84 tests passed`; typecheck passed (`tsc --noEmit`, exit 0).
- Ruff on the Python files changed in this round: passed. Targeted mypy: passed with no issues.
- `git diff --check`: passed. The known branch baseline remains 7 unchanged Ruff `E501` diagnostics in `src/umbral/application/radar/service.py` when checking all historical changed Python paths.
- No scoring formula, ranking, hard-filter, activation, notification, database model, migration or LLM decision behavior changed.

**Final conclusion:** the two Major findings from this re-review are resolved. The branch is ready for handoff, subject to the documented baseline diagnostics and review limitations.
