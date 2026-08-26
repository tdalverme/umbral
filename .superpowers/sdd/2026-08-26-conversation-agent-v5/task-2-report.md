# Task 2 Report — V5.1 Published Contracts and Typed Acts

## Implementation

Published V5 JSON Schema draft 2020-12 contracts for context, interpretation,
state, reply, and graph topology. The interpretation schema has ten closed
`oneOf` act branches with canonical JSON discriminator strings, catalogued
radar hard-filter keys (`budget_max`, `zones`, `min_rooms`), the existing
feedback vocabulary, evidence spans, and no generic target/payload fields.

Added frozen, slotted Python contracts under
`umbral.application.conversation.v5`. They include the required context views,
typed acts, ordered `ConversationActV5` alias, interpretation, decisions,
plans, execution outcomes, and turn result. `TurnContextV5.authorizes()` only
compares opaque snapshot references; it neither parses nor fetches objects.

## RED

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py -q --basetemp .pytest-task-2-red
```

Output:

```text
==================================== ERRORS ====================================
__ ERROR collecting tests/unit/application/conversation/v5/test_contracts.py __
ImportError while importing test module '.../tests/unit/application/conversation/v5/test_contracts.py'.
E   ModuleNotFoundError: No module named 'umbral.application.conversation.v5'
=========================== short test summary info ===========================
ERROR tests/unit/application/conversation/v5/test_contracts.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 1.14s
```

The expected failure was the missing V5 contract package.

## GREEN

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py -q --basetemp .pytest-task-2-green
```

Output:

```text
...........                                                              [100%]
11 passed in 0.40s
```

## Verification

```text
$ pytest tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py tests/contract/test_agent_contracts_v4.py -q --basetemp .pytest-task-2-verify
..................                                                       [100%]
18 passed in 0.50s

$ ruff check src/umbral/application/conversation/v5 tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py
All checks passed!

$ mypy src/umbral/application/conversation/v5 tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py
Success: no issues found in 4 source files
```

## Files

- `contracts/agent/v5/context-schema-v5.json`
- `contracts/agent/v5/interpretation-schema-v5.json`
- `contracts/agent/v5/state-schema-v5.json`
- `contracts/agent/v5/reply-schema-v5.json`
- `contracts/agent/v5/graph-topology-v5.json`
- `src/umbral/application/conversation/v5/__init__.py`
- `src/umbral/application/conversation/v5/contracts.py`
- `tests/contract/test_agent_contracts_v5.py`
- `tests/unit/application/conversation/v5/test_contracts.py`

## Self-review

- Confirmed every published V5 schema has draft 2020-12 metadata, contract
  version `5`, required fields, and closed top-level objects.
- Confirmed the ten interpretation branches are closed, exhaustive, and use
  exactly the prescribed discriminator strings.
- Confirmed V4 contract regression tests pass and there are no V4 contract,
  policy, or graph edits in this task.
- Confirmed dataclasses are frozen/slotted, evidence boundaries reject invalid
  spans, and opaque reference authorization is snapshot-membership only.

## Concerns

None. Future tasks will add policy, commands, execution, and persistence; this
task intentionally contains no such behavior.

## Fix Round 1 — Normative topology, typed filters, and closed commands

### Root cause

The topology schema restricted each node name but did not require the complete
set, and its edge endpoints were unconstrained strings. The context filter
value used a broad union without conditioning it on `filter_key`; the
interpretation set-filter branch had the same gap. Finally, `TurnPlanV5`
declared an unrestricted `tuple[object, ...]` before a closed command union
exists.

### RED

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py -q --basetemp .pytest-task-2-fix-1-red
```

Output:

```text
........FFF....FF.......FFFF                                             [100%]
9 failed, 19 passed in 0.97s
```

The failing cases showed that missing graph nodes, an external edge endpoint,
the direct `interpret_turn -> execute_segment` edge, numeric-filter arrays,
invalid Python filter values, and `tuple[object, ...]` were all accepted.
An additional focused RED run showed that an unpublished Python filter key was
accepted; the final GREEN run confirms it is now rejected.

### GREEN

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py tests/contract/test_agent_contracts_v4.py -q --basetemp .pytest-task-2-fix-1-final
```

Output:

```text
....................................                                     [100%]
36 passed in 1.01s
```

### Changes and verification

- Required the exact nine-node, ten-edge graph shape through bounded unique
  arrays and a closed `oneOf` edge vocabulary; added a valid graph fixture and
  rejection coverage for missing nodes, unknown endpoints, and the forbidden
  direct edge.
- Closed filters by key in context and set-filter interpretation contracts:
  `budget_max` is numeric, `min_rooms` is integer, and `zones` is a bounded
  array of strings. `HardFilterV5` and `SetFilter` now apply matching runtime
  validation.
- Replaced `TurnPlanV5.commands: tuple[object, ...]` with the deliberately
  uninhabited `tuple[Never, ...]` pending Task 6's closed command union.
- `ruff check` passed; `mypy` reported `Success: no issues found in 4 source
  files`; all V5 JSON schemas passed Draft 2020-12 meta-validation; `git diff
  --check` passed.

## Fix Round 2 — Runtime parity for zones and commands

### Root cause

The shared Python filter validator only checked that zones were strings; it
missed the JSON Schema's non-empty-string and maximum-fifteen-item limits.
`TurnPlanV5` used an uninhabited static type but had no runtime guard, so a
cast or untyped caller could still supply command objects.

### RED

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5/test_contracts.py -q --basetemp .pytest-task-2-fix-2-red
```

Output:

```text
...........FF..FF.F                                                      [100%]
5 failed, 14 passed in 0.28s
```

The failures covered empty and sixteen-item zone tuples for `HardFilterV5` and
`SetFilter`, plus runtime acceptance of a non-empty `TurnPlanV5.commands`.

### GREEN

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/contract/test_agent_contracts_v5.py tests/unit/application/conversation/v5/test_contracts.py tests/contract/test_agent_contracts_v4.py -q --basetemp .pytest-task-2-fix-2-final
```

Output:

```text
...........................................                              [100%]
43 passed in 1.03s
```

### Changes and verification

- `HardFilterV5` and `SetFilter` now reject empty zone strings and more than
  fifteen zones, matching the published JSON shape. Existing scalar-type
  validation continues to run through the same shared validator.
- `TurnPlanV5.__post_init__` rejects every non-empty `commands` tuple until
  Task 6 replaces the temporary `Never` field with the closed command union.
- `ruff check` passed; `mypy` reported `Success: no issues found in 4 source
  files`; all V5 JSON schemas passed Draft 2020-12 meta-validation; `git diff
  --check` passed.
