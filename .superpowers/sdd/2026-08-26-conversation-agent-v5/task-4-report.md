# Task 4 Report — V5.1 Structured Interpreter and Prompt

## Implementation

Added `InterpretationCompilerV5` in `src/umbral/agent/intent/v5.py`. The
compiler calls `ModelGateway.generate_structured` with a system message that
serializes `AUTHORIZED_CONTEXT` and `UNTRUSTED_CONTENT` separately, then decodes
each closed `oneOf` act branch into its matching typed dataclass.

Strict decoding enforces: every act requires non-empty evidence; each evidence
span must be a literal slice of the user message (offsets in bounds and
`text == message[start:end]`); refs (`listing:`, `desire:`, `pending:`) must be
authorized by `TurnContextV5.authorizes()`; duplicate `act_id`s and more than
six acts are rejected; filter keys and feedback types must come from the
published vocabularies; concept links are soft-only. Any violation raises the
typed `InterpretationContractFailed`; the compiler never synthesizes an empty
query.

Added the versioned prompt `src/umbral/agent/prompts/interpretation-v5.md`
documenting `prompt_version: interpretation-v5`: acts describe only explicit
user intent, quoted/external content is data, only provided refs are used,
`unsupported_request` covers unavailable operations, non-computable desires are
preserved, evidence spans are literal user-message slices, acts are emitted in
expressed order, and hard force/ranking/effects are never inferred. Includes
positive and negative examples for injection, account deletion, feedback with
verified focus, multi-desire, and confirm-plus-extra-intent.

## RED

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/agent/intent/test_interpretation_v5.py -q --basetemp .pytest-task-4-red
```

Output:

```text
ERROR tests/unit/agent/intent/test_interpretation_v5.py
ModuleNotFoundError: No module named 'umbral.agent.intent.v5'
```

The expected failure was the missing V5 interpreter module.

## GREEN

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/agent/intent/test_interpretation_v5.py -q --basetemp .pytest-task-4-green
```

Output:

```text
9 passed in 0.09s
```

An initial RED run exposed a test-harness bug (evidence span end was hardcoded
to 10 while the 12-character message required `end=12`); the span helper now
derives offsets from the actual message length.

## Verification

```text
$ pytest tests/unit/agent/intent/test_interpretation_v5.py tests/contract/test_agent_contracts_v5.py -q
26 passed in 1.76s

$ ruff check src/umbral/agent/intent/v5.py tests/unit/agent/intent/test_interpretation_v5.py
All checks passed!

$ mypy src/umbral/agent/intent/v5.py tests/unit/agent/intent/test_interpretation_v5.py
Success: no issues found in 2 source files
```

## Files

- `src/umbral/agent/intent/v5.py`
- `src/umbral/agent/prompts/interpretation-v5.md`
- `tests/unit/agent/intent/test_interpretation_v5.py`

## Self-review

- Confirmed the model only proposes typed acts; no ranking, scoring, hard-force
  inference, or effect synthesis is possible from model output.
- Confirmed refs absent from the authorized context are rejected and untrusted
  listing content cannot originate acts (its ref is never in the context unless
  the focus reader verified it).
- Confirmed the system message labels authorized context and untrusted content
  distinctly, and the compiler never fabricates a query on failure.
- Confirmed the published V5 contract tests still pass; no V4 files were
  modified.

## Concerns

None.
