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
