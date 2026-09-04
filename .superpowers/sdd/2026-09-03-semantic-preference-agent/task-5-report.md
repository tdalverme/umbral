# Task 5 report — ordered hard-filter confirmation

## RED / GREEN

- RED: `PYTHONPATH=src ..\\..\\.venv\\Scripts\\python.exe -m pytest tests/unit/application/conversation/v5/test_policy_desires.py tests/unit/application/conversation/v5/test_service.py -q`
  - Result: 2 failed, 11 passed. The failures proved that initial hard filters were applied and that execution stopped at the first proposal.
- GREEN (focused): `PYTHONPATH=src ..\\..\\.venv\\Scripts\\python.exe -m pytest tests/unit/application/agent/tools/test_proposals.py tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 -q`
  - Result: 108 passed.
- Contract/model check: `PYTHONPATH=src ..\\..\\.venv\\Scripts\\python.exe -m pytest tests/unit/infrastructure/test_db_model_contract.py tests/contract/test_agent_contracts_v5.py -q`
  - Result: 26 passed.
- Compile and whitespace: `PYTHONPATH=src ..\\..\\.venv\\Scripts\\python.exe -m compileall -q src\\umbral` and `git diff --check`
  - Result: passed.

## Delivered

- Every valid hard set/clear is proposed with `filter.requires_confirmation`; no hard filter versions a radar before approval.
- Soft desires run before the original-order hard-filter proposal queue.
- Proposals persist their origin act and queue ordinal; the context exposes the queue head with ordinal and total.
- Approval/rejection consumes one proposal; remaining queue entries are rebased after approval so the next step applies against the new radar version.
- Same-key corrections derive a traceable successor at the same ordinal; other keys append.
- Existing receipt idempotency remains the execution boundary, so replay cannot duplicate proposal execution.

## Commit

- `feat: confirm hard filters one step at a time`

## Self-review

- Reviewed the V5 policy, executor, turn ordering, context/graph serialization, proposal repository/model and migration.
- Migration `0023_conversation_v5_proposal_queue` is additive; no prior migration was edited.

## Concerns

The required aggregate suite was invoked. Its unit and non-container chat tests passed, but six `test_session_repo.py` integration tests could not start because Docker Desktop's `//./pipe/docker_engine` was unavailable. This is an environment prerequisite, not an assertion failure.

## Review round 1

- The graph now interrupts with only the durable queue head and, on resume, calls the V5 pending resolver with the explicit approve/reject decision before reloading context. A remaining head causes the next interrupt; no old message is reinterpreted.
- Migration 0023 now backfills nonempty legacy act ids and positive pending ordinals, with a database check constraint.
- Focused verification: `tests/unit/agent/test_graph_v5.py`, `tests/contract/test_agent_contracts_v5.py`, and `tests/unit/infrastructure/test_db_model_contract.py` — 30 passed.

## Review round 2

- Proposal defaults now satisfy the durable database invariant (`legacy`, ordinal `1`).
- Queue access is exposed as an explicit proposal-service reader; V5 context no longer reaches through a repository dynamically.
- A turn reloads its authorized context after creating pending proposals, so its result and the graph confirmation payload observe the durable head.

## Review round 3 / continuation

- Added durable `queue_total` metadata and migration `0024_conversation_v5_proposal_total`; the repository updates all pending rows under the session lock so ordinal/total remains coherent after consuming a head.
- Added transactional `enqueue_pending` and `supersede_and_insert` repository ports. PostgreSQL locks the durable chat-session row, covering empty-queue races and making correction lineage atomic. The local repository implements the same semantics for the playground.
- Graph/context preserve the durable step metadata, and rejected pending resolutions now remain `rejected` outcomes (with `user` reason) for replies and audit.
- RED: `$env:PYTHONPATH='src'; & '..\\..\\.venv\\Scripts\\python.exe' -m pytest tests/unit/application/agent/tools/test_proposals.py -q` — 3 failed, 20 passed; failures covered missing durable total and unused atomic ports.
- GREEN: `PYTHONPATH=src ..\\..\\.venv\\Scripts\\python.exe -m pytest tests/unit/application/agent/tools/test_proposals.py tests/unit/infrastructure/conversation/v5/test_radar_executor.py tests/unit/agent/test_graph_v5.py tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 tests/migrations/test_upgrade_and_drift.py tests/unit/infrastructure/test_db_model_contract.py tests/contract/test_agent_contracts_v5.py -q` — 126 passed, 2 warnings.
- Alembic offline upgrade SQL and `git diff --check` passed. The Docker-backed `tests/integration/chat` suite remains unavailable in this environment (Docker engine pipe did not respond); no assertion result was claimed.
