# Task 9 Report — V5.6 Ordered Orchestration, Confirmation, and Idempotency

## Implementation

Added the ordered V5 turn module `ConversationTurnV5` in
`src/umbral/application/conversation/v5/service.py` plus the durable receipt
layer in `receipts.py`, a DB model, a SQLAlchemy repository, and migration
`0022_conversation_v5_command_receipts`.

**Receipts.** `CommandReceiptStore` port with `start/complete/fail`;
`ReceiptStart` carries `new | already_applied | in_progress`. The
`execute_with_receipt` guard: replays return the stored result for
`already_applied`, never re-execute for `in_progress` (returns
`execution.reconciliation_required`, handled operationally), records
`applied`/`pending` results as completed receipts, and marks failed receipts
for rejected/errored executions (which may be retried).

**Orchestration.** `process(user_id, session_id, message_id, message_text,
correlation_id) -> ConversationTurnResultV5` follows the design's multi-act
semantics: pending resolution is the first segment (via the `PendingResolverV5`
port, using `SearchProfileUpdateProposals` native idempotency), the context is
reloaded after that state-changing segment, remaining typed acts are re-planned
against the refreshed context, safe acts execute in expressed order with
idempotency keys `conversation-v5:{session_id}:{message_id}:{act_id}` (stable
`message_id` required), and the segment stops at a pending or clarification
decision; later acts are marked `not_executed`. Provider/interpretation/policy/
execution failures produce typed `failure_stage` results and never execute
anything after the failure; `execution.stale_context` maps to
`needs_clarification`.

**Audit.** Added the narrow `TurnAuditWriterV5.record(result, versions)` port;
the service persists the audit envelope after execution. Audit failure is
observable (the result carries `contract_or_fixture_failure`) and never reruns
already-applied commands.

**DB.** `conversation_v5_command_receipts` table keyed by `idempotency_key`
with `session_id`, `message_id`, `act_id`, `command_kind`, closed status enum
`started|applied|failed`, serialized safe result (JSONB), timestamps, and
correlation id; `SqlAlchemyCommandReceiptStore` implements the port over the
existing session-factory pattern; migration `0022` creates the table, index,
and enum, and downgrades guard-free (no data to preserve).

## RED

The focused suites failed at collection because the turn module, receipts, and
repository did not exist.

## GREEN

The first GREEN run exposed two defects: the policy port was invoked as
`self.policy.plan(...)` although the policy is a plain function (fixed by making
`TurnPolicyV5` a callable protocol), and `_propose` lost its class indentation
when the feedback adapter was added (fixed). After correction:

```text
$ pytest tests/unit/application/conversation/v5/test_service.py tests/unit/application/conversation/v5/test_receipts.py tests/unit/infrastructure/conversation/v5/test_receipt_repository.py tests/unit/application/agent/tools/test_proposal_transitions.py tests/unit/application/agent/tools/test_proposals.py tests/unit/infrastructure/test_db_model_contract.py -q
38 passed in 1.40s
```

## Verification

```text
$ pytest tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 tests/unit/application/conversation tests/unit/infrastructure/test_conversation_composition.py tests/unit/infrastructure/test_db_model_contract.py -q
76 passed in 1.50s

$ ruff check src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 src/umbral/infrastructure/db/models/conversation_v5.py src/umbral/infrastructure/db/repositories/conversation_v5.py alembic/versions/0022_conversation_v5_command_receipts.py tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
All checks passed!

$ mypy src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
Success: no issues found in 21 source files
```

## Files

- `src/umbral/application/conversation/v5/service.py`
- `src/umbral/application/conversation/v5/receipts.py`
- `src/umbral/application/conversation/v5/ports.py` (service ports)
- `src/umbral/infrastructure/conversation/v5/executor.py`
  (`ProposalsPendingResolverV5`)
- `src/umbral/infrastructure/db/models/conversation_v5.py`
- `src/umbral/infrastructure/db/repositories/conversation_v5.py`
- `alembic/versions/0022_conversation_v5_command_receipts.py`
- `tests/unit/application/conversation/v5/test_service.py`
- `tests/unit/application/conversation/v5/test_receipts.py`
- `tests/unit/infrastructure/conversation/v5/test_receipt_repository.py`

## Self-review

- Confirmed confirm-plus-extra-intent reloads context exactly once after the
  pending segment and executes both segments; pending acts stop the tail while
  prior safe acts stay applied.
- Confirmed retries reuse idempotency keys via receipts (no re-execution),
  provider failures execute nothing, and stale contexts return clarification.
- Confirmed a receipt left `started` after a crash reports
  `execution.reconciliation_required` instead of risking a duplicate mutation.
- Confirmed proposals and DB-model contract suites pass unchanged; no V4
  production files were modified.

## Concerns

The receipt table uses `idempotency_key` as its primary key (the plan asked
for a unique key; the natural key is unique by construction). The audit writer
port is wired in the service; its durable implementation is left to the
composition task.