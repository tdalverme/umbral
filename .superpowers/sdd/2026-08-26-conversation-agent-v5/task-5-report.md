# Task 5 Report — V5.2 Deterministic Policy and Safe Read Path

## Implementation

Added `plan_turn_v5(user_message, context, interpretation) -> TurnPlanV5` in
`src/umbral/application/conversation/v5/policy.py`. The policy is pure and
deterministic: it dispatches over the typed act dataclasses (no generic
dictionary inspection) and returns exactly one `ActDecisionV5` per act with a
stable reason code.

Safety checks run before any act-specific rule:

1. **Capability** — an act whose kind is not in `context.allowed_capabilities`
   is rejected with `capability.not_allowed`.
2. **Untrusted evidence provenance** — if any act evidence span text matches an
   `untrusted_content` entry, the act is rejected with `act.untrusted_evidence`
   (invariant 2).
3. **Explicit evidence** — an act with empty evidence or evidence that is not a
   literal slice of the user message is rejected with `act.missing_evidence`
   (invariant 1).

Act rules: `Query` is applied with no durable command and never mutates
(invariant 4); `Query` combined with any mutation in the same turn becomes
`needs_clarification` (`act.query_with_mutation`) rather than guessing an
answer against a changing state; `UnsupportedRequest` is rejected with
`request.unsupported` and is never approximated as another mutation (invariant
5); `CreateRadar` applied only when unbound, rejected `radar.already_bound`
otherwise; `SetFilter` applied for new/no-op filters, `pending` with
`filter.changes_existing_hard_filter` when changing an active hard filter;
`ClearFilter` `pending` with `filter.removes_hard_filter` when active, rejected
`filter.not_active` otherwise; desire/feedback/pending acts require an
authorized ref and reject with `desire.not_active`,
`feedback.listing_not_authorized`, or `pending.not_found` when the ref is
absent (invariant 3).

Commands remain `()` because `TurnPlanV5.commands` is the deliberately
uninhabited `tuple[Never, ...]`; Task 6 publishes the closed command union.

## RED

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5/test_policy_safety.py tests/unit/application/conversation/v5/test_policy_queries.py -q --basetemp .pytest-task-5-red
```

Output:

```text
ERROR tests/unit/application/conversation/v5/test_policy_safety.py
ModuleNotFoundError: No module named 'umbral.application.conversation.v5.policy'
```

The expected failure was the missing policy module.

## GREEN

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/conversation/v5 -q --basetemp .pytest-task-5-green
```

Output:

```text
26 passed in 0.20s
```

The first GREEN run surfaced an argument-order bug in the internal rejection
helper (the reason string landed in the `status` slot) and a test fixture
span/offset mismatch for the multi-act message; both were corrected.

## Verification

```text
$ pytest tests/unit/application/conversation/v5 tests/unit/application/conversation/test_conversation_policy.py -q
39 passed in 0.20s

$ ruff check src/umbral/application/conversation/v5/policy.py tests/unit/application/conversation/v5
All checks passed!

$ mypy src/umbral/application/conversation/v5/policy.py tests/unit/application/conversation/v5
Success: no issues found in 4 source files
```

## Files

- `src/umbral/application/conversation/v5/policy.py`
- `tests/unit/application/conversation/v5/test_policy_safety.py`
- `tests/unit/application/conversation/v5/test_policy_queries.py`

## Self-review

- Confirmed untrusted content cannot supply mutation evidence and absent or
  non-matching evidence is rejected before act rules.
- Confirmed `Query` produces no durable command and `UnsupportedRequest` is
  never approximated as a withdrawal or any other mutation.
- Confirmed refs must exist in the authorized context (`desire.not_active`,
  `feedback.listing_not_authorized`, `pending.not_found`).
- Confirmed the unchanged V4 policy suite (13 tests) still passes; no V4 files
  were modified.

## Concerns

The plan names "query-plus-mutation contradiction" without an exact predicate;
this task implements it as: a `Query` act in a turn that also contains any
durable mutation is marked `needs_clarification` (`act.query_with_mutation`) so
the agent never guesses whether to answer from the pre- or post-mutation state.
Mutations in such a turn still receive their normal decisions. This does not
conflict with the multi-act confirmation flow in Task 9.
