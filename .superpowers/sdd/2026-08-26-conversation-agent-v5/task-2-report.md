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
