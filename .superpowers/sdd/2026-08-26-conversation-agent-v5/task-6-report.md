# Task 6 Report — V5.3 Radar Creation and Filter Commands

## Implementation

Published the closed radar command union in
`src/umbral/application/conversation/v5/contracts.py`:
`CreateRadarCommand(act_id, name)`, `SetFilterCommand(act_id, filter_key,
value, expected_profile_version)`, `ClearFilterCommand(act_id, filter_key,
expected_profile_version)`, and the `CommandV5` union. `TurnPlanV5.commands`
now carries `tuple[CommandV5, ...]`; the temporary `Never` field and its
stopgap guard are replaced by a runtime guard that only accepts members of the
closed union.

Extended `plan_turn_v5` in `policy.py` to emit commands: `CreateRadar` applied
when unbound with a `CreateRadarCommand` (rejected `radar.already_bound` when
bound); `SetFilter` applied for new/no-op filters and `pending` with
`filter.changes_existing_hard_filter` when changing an active hard filter,
always carrying `expected_profile_version` from the context; `ClearFilter`
`pending` with `filter.removes_hard_filter` when active; both filter acts are
rejected `radar.not_bound` without a bound radar. New filters remain safe
immediate commands; replacing or clearing an active hard filter always goes
through the proposal path, never a direct mutation.

Added `EffectExecutorV5` in `infrastructure/conversation/v5/executor.py`,
routing commands only through explicit application interfaces: radar creation
and session binding through `RadarService.create_profile` +
`ChatService.bind_profile`; immediate new filters through
`RadarService.version_profile(expected_version=...)`; material changes through
`SearchProfileUpdateProposals.propose(...)`; version conflicts map to
`execution.stale_context`.

## Idempotency decision

The plan asks to reuse the available application idempotency mechanism rather
than caching in the agent. For radar creation, `RadarService.create_profile`
has no key-based idempotency, so rather than adding a repository-backed key to
the shared V4 service, the executor treats the durable session binding
(FR-003: one radar per session) as the native idempotency mechanism: a replay
after the first create finds the bound session and returns the existing radar
without creating a second profile. This is durable (not agent-cached), keeps
the V4 radar service behaviorally unchanged, and satisfies the
`create_calls == 1` idempotency test. The plan's alternative (adding an
idempotency key to `RadarService`) remains available if session uniqueness is
ever relaxed.

## RED

The focused suites failed at collection because the command union and executor
did not exist (missing `umbral.infrastructure.conversation.v5.executor` and
`CommandV5`).

## GREEN

```text
$ pytest tests/unit/infrastructure/conversation/v5/test_radar_executor.py tests/unit/application/radar/test_profile_service.py tests/unit/application/agent/tools/test_proposals.py tests/unit/application/conversation/v5 tests/contract/test_agent_contracts_v5.py -q
76 passed in 1.70s
```

## Verification

```text
$ ruff check src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
All checks passed!

$ mypy src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
Success: no issues found in 12 source files
```

## Files

- `src/umbral/application/conversation/v5/contracts.py` (command union)
- `src/umbral/application/conversation/v5/policy.py` (command emission)
- `src/umbral/infrastructure/conversation/v5/executor.py`
- `tests/unit/infrastructure/conversation/v5/test_radar_executor.py`
- `tests/unit/application/conversation/v5/test_policy_safety.py`
- `tests/unit/application/conversation/v5/test_contracts.py` (closed-union tests)

## Self-review

- Confirmed replacing or clearing an active hard filter never mutates directly;
  it always creates a durable pending proposal.
- Confirmed every radar command carries `expected_profile_version` from the
  context and version conflicts map to `execution.stale_context`.
- Confirmed radar creation is idempotent through the durable session binding
  and the session is bound to the created radar (FR-003).
- Confirmed `RadarService`/`proposals` regression suites (76 tests) pass
  unchanged; no V4 production files were modified.

## Concerns

`contracts.py` was modified even though the plan's Task 6 file list omits it:
this is required to replace the temporary `Never` command field with the
closed command union, as the Task 2 fix-round notes anticipated.
