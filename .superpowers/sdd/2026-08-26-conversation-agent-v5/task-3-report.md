# Task 3 Report — V5.1 Authorized Context Assembler

## Implementation

Added the narrow V5 ports (`application/conversation/v5/ports.py`): the
`ContextReaderV5` port, the `PendingActionReaderV5` port, the
`FocusedEntityReader` port, and the typed `ContextAssemblyFailed` error with
`reason_code`. The focus port returns a `FocusedListingV5` value carrying the
listing UUID and its document text: the plan's `FocusedEntityV5` carries no
text, and the assembler must keep the untrusted listing text separate from the
user-authored message, so the port value carries the text while the published
context still exposes only the opaque `FocusedEntityV5(entity_ref)`.

Implemented `ContextAssemblerV5` in `infrastructure/conversation/v5/context.py`
over the explicit services: it resolves the chat session, the bound radar
(ref + version + normalized `current_filters`), active preference expressions
as authorized `desire:` refs (with soft structured/semantic bindings exposed as
concept links; unresolved and hard bindings are not links), the durable pending
proposal as a `pending:` ref, and the focus-reader-verified listing as an
authorized `listing:` ref with its text as `untrusted_content`
(`may_supply_evidence` fixed `False`).

Also added `ProposalsPendingReaderV5`, which adapts the durable proposal store
to the `PendingActionReaderV5` port, mirroring the V4 `ProposalsPendingReader`.

## RED

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/conversation/v5/test_context.py -q --basetemp .pytest-task-3-red
```

Output:

```text
ERROR tests/unit/infrastructure/conversation/v5/test_context.py
ModuleNotFoundError: No module named 'umbral.application.conversation.v5.ports'
```

The expected failure was the missing V5 ports and context adapter.

## GREEN

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/conversation/v5/test_context.py tests/unit/application/conversation/v5/test_contracts.py -q --basetemp .pytest-task-3-green
```

Output:

```text
28 passed in 0.31s
```

The first GREEN run surfaced test-harness issues (listing-focused tests bound a
session to a nonexistent profile, triggering the ownership path; the desire
view used an unresolved binding) and one semantic refinement: concept links are
only emitted for soft structured/semantic bindings, never for unresolved or
hard ones. After adjusting the tests and that guard, all cases pass.

## Verification

```text
$ pytest tests/unit/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/test_conversation_composition.py tests/unit/application/conversation -q
33 passed in 0.37s

$ ruff check src/umbral/application/conversation/v5/ports.py src/umbral/infrastructure/conversation/v5 tests/unit/infrastructure/conversation/v5/test_context.py
All checks passed!

$ mypy src/umbral/application/conversation/v5/ports.py src/umbral/infrastructure/conversation/v5 tests/unit/infrastructure/conversation/v5/test_context.py
Success: no issues found in 4 source files
```

## Files

- `src/umbral/application/conversation/v5/ports.py`
- `src/umbral/infrastructure/conversation/v5/__init__.py`
- `src/umbral/infrastructure/conversation/v5/context.py`
- `tests/unit/infrastructure/conversation/v5/test_context.py`

## Self-review

- Confirmed `TurnContextV5` only contains focus-reader-verified `listing:`
  refs, active `desire:` refs, the durable `pending:` ref, and the bound radar
  ref; `authorizes()` remains snapshot-membership only.
- Confirmed untrusted listing text is carried as `UntrustedContentV5` with
  `may_supply_evidence` fixed `False`, never merged into the user message.
- Confirmed ownership failures raise typed `context.ownership_rejected` and are
  never degraded into an unbound context; other radar read failures raise
  typed `context.radar_unreadable`; a missing radar is a legitimate unbound
  context, not an error.
- Confirmed the V4 conversation composition and policy suites still pass
  unchanged; no V4 files were modified.

## Concerns

The focus reader carries listing text through the port value rather than the
published `FocusedEntityV5` contract type, because that contract carries no
text. The semantic requirement (verified listing refs plus untrusted listing
data kept separate from user intent) is preserved.
