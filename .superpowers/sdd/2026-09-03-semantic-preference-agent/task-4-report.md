# Task 4 report — one semantic conversation interpreter

## Result

`InterpretationCompilerV5` now receives a trusted per-build concept catalog,
publishes it in a delimited `CONCEPT_CATALOG` prompt section, and validates
every returned concept ref against that same snapshot. When supported by the
schema, the snapshot keys are also published as the output enum. The compiler
keeps an unmapped desire with no links, forces one independently evidenced
`express_desire` per mapped concept, and preserves polarity and intensity.

Production V5 wiring snapshots the active concept registry (canonical key,
name, matcher, computability, and alias examples) before constructing both V5
interpreters. The prompt now explicitly reserves `set_filter` for literal hard
filters; qualitative and environment wishes stay soft desires.

## RED evidence

First added the V5 tests for a catalog-only test concept, empty links despite
an alias example, ordered independent desires, and an invented concept ref.
Ran:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
& '..\..\.venv\Scripts\python.exe' -m pytest tests/unit/agent/intent/test_interpretation_v5.py -q
```

Result: `4 failed, 15 passed`. Each new case failed because
`InterpretationCompilerV5` had no `concept_catalog` parameter.

Added the one-concept-per-`express_desire` regression and ran the same unit
suite again before its implementation. Result: `1 failed, 19 passed`; the
compiler accepted two concept links in one desire, as expected for RED.

## GREEN evidence

Required focused command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
& '..\..\.venv\Scripts\python.exe' -m pytest tests/unit/agent/intent/test_interpretation_v5.py tests/integration/chat/test_semantic_preferences.py tests/architecture/test_agent_boundaries.py -q
```

Result: `34 passed in 0.33s`.

The integration seam uses a scripted gateway that never branches on message
text. It now covers four additional alias-absent paraphrases (`sol`,
`estruendo`, `subte caminando`, and `verde a pocas cuadras`) and asserts the
same persisted catalog-backed effects.

Additional compatibility check:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
& '..\..\.venv\Scripts\python.exe' -m pytest tests/unit/agent/tools/test_propose_preference.py tests/unit/agent/tools/test_propose_apply.py tests/contract/test_preferences_vocabulary.py tests/contract/test_agent_graph_topology_v3.py -q
```

Result: `27 passed in 4.64s`.

`git diff --check` completed without whitespace errors (only Git's existing
line-ending conversion warnings were emitted).

## Deleted path and wiring

- `src/umbral/application/agent/tools/preference_interpreter.py`
- `src/umbral/infrastructure/agent/tools/preferences_loader.py`
- `_interpret_preference`, `_propose_preference_llm`, and their dead helpers
- `tests/unit/application/agent/tools/test_preference_interpreter.py`
- LLM phrase-interpreter coverage from `test_propose_preference.py`

The legacy vocabulary loader moved to its application module solely to retain
the existing V3 tool-contract tests after deleting the infrastructure loader;
the removed LLM phrase resolver has no production path.

## Self-review

- The only V5 semantic resolver is the full-turn compiler; it has no regex,
  alias lookup, or normalized-phrase fallback for concept resolution.
- An invented catalog ref fails before a typed act is returned or persistence
  can run.
- Empty `concept_links` remain valid for an explicit unmapped desire, even if
  an alias appears in the prompt catalog.
- Each mapped V5 desire has one catalog concept and carries its literal act
  evidence into the persisted binding path.
- Schema enrichment works opportunistically; deterministic post-validation is
  always applied.

## Concerns

The V5 compiler permits an empty catalog for isolated callers, in which case
all non-empty concept links fail closed. Production V5 wiring always supplies
the active registry snapshot. The focused architecture suite verifies no
forbidden layer imports; a repository-wide lint run still reports pre-existing
E402/E501 diagnostics in files with imports/logging outside this task's scope.

## Commit

`refactor: use one semantic conversation interpreter`

## Round 1 review fixes

The follow-up findings were addressed without removing the legacy V3 lexical
resolver (that remains scoped to Task 7):

- `_build_v5_concept_catalog` now rejects an empty active registry before the
  V5 interpreter is constructed; `test_v5_catalog_loader_rejects_an_empty_active_registry`
  covers the fail-closed behavior.
- `V5EvalTrialExecutor` now snapshots the published criteria seed once and
  passes the complete catalog (canonical key, description, matcher metadata,
  computability, and aliases) to `InterpretationCompilerV5`. The eval test
  compares the delivered key set to the full published seed and checks
  representative housing and environmental concepts.
- `scripts/local-llm-smoke.ps1` now calls the V5 full-turn interpreter and the
  canonical `load_concepts_seed` loader; it no longer imports deleted V3
  preference interpreter/loader modules. The smoke contract test guards both
  imports and the active seed path. The new test was RED (`1 failed`) before
  the loader change and GREEN (`1 passed`) afterward.
- The qualitative/environmental regression exercises the structured gateway
  boundary: the fake gateway returns model-shaped `express_desire` acts
  without branching on user text, the test verifies the exact user message and
  prompt rule sent to the gateway, and asserts both acts remain soft desires.

Focused verification after the fixes:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
& '..\\..\\.venv\\Scripts\\python.exe' -m pytest tests/unit/agent/intent/test_interpretation_v5.py tests/integration/chat/test_semantic_preferences.py tests/architecture/test_agent_boundaries.py -q
# 35 passed in 0.30s

$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
& '..\\..\\.venv\\Scripts\\python.exe' -m pytest tests/unit/infrastructure/agent/test_production_v5.py tests/integration/agent_evals/test_v4_same_path.py tests/contract/test_local_llm_smoke_contract.py -q
# 18 passed in 0.57s
```

`git diff --check` reported no whitespace errors (only existing LF/CRLF
conversion warnings). Self-review found no new production text inspection,
alias fallback, or V3 resolver deletion. The remaining concern is that the
local smoke requires managed-model environment variables and was validated at
the script-contract level rather than against a live provider.

Round 1 fix commit: `18655e1 fix: close task 4 semantic interpreter review findings`.
