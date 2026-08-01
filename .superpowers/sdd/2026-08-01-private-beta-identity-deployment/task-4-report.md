# Task 4 report — identity persistence port

## Changed files

- `src/umbral/application/identity/ports.py`: replaced exposed mutable collections and lock with behavioral persistence operations.
- `src/umbral/application/identity/access.py`, `authorization.py`, `administration.py`, `retention.py`: callers use only the port and transactions.
- `src/umbral/infrastructure/db/repositories/identity.py`: made in-memory state private, with transaction rollback including provider-event dedupe and audit.
- `src/umbral/ops/identity.py`, `src/umbral/ops/smoke.py`: use narrow port queries rather than storage internals.
- `tests/contract/test_identity_store.py`, `tests/support/identity.py`, and identity callers: behavioral conformance and migrated usages.

## RED / GREEN

RED was observed with `pytest tests/contract/test_identity_store.py`: all three tests failed because `save_invitation` and `append_provider_audit_once` did not exist.

GREEN was observed after the minimal adapter implementation: `3 passed` for the new store contract. The contract verifies save/load records, atomic webhook dedupe plus audit append, and state-plus-audit rollback.

`latest_attempt()` was removed after review because it was only helping tests. Test composition now observes the real submitted job reference, then reloads the attempt through `store.attempt()`.

## Verification

- `ruff check src/umbral/application/identity src/umbral/infrastructure/db/repositories/identity.py tests/contract/test_identity_store.py`: passed.
- `rg -n "store\.(invitations|users|links|roles|requests|attempts|sessions|audits|lock)" src/umbral/application/identity`: no matches.
- Focal contract: `3 passed`.
- Full Task 4 non-container command (`-k "not postgres"`): `46 passed, 2 deselected`. The two intentionally unexecuted Docker nodes are `tests/integration/identity/test_magic_link_flow.py::test_postgres_invitation_preload_and_rate_limit` and `tests/integration/identity/test_magic_link_flow.py::test_postgres_transaction_rolls_back_request_and_audit`; Docker access to `//./pipe/docker_engine` is denied locally.

## Self-review / concerns

- Review round 1 added copy-on-write adapter coverage for job submission. It first failed with an unsaved `job_execution_id` and `pending` state after submission failure; both transitions now call `save_attempt` explicitly.
- The conformance suite now covers `current_attempt`, exact recent-request window behavior, and deep/reentrant rollback of provider-event dedupe. Magic-link integration asserts exact exported-identity/session cardinality through existing production operations.
- Fresh non-container verification after the review fixes: `50 passed, 2 deselected`.
- Review round 2 adds reloaded transitions for every record type, multiple-current-attempt selection/filtering, an attempt-save spy for the rate limiter, exact link/role/session cardinality through existing production operations, and rollback proof through `recent_requests == 0`. Fresh result: `51 passed, 2 deselected`.
- Review round 3 corrected the rollback check to fingerprint `person@example.com`, the email used by the failed request. A deliberate `== 1` mutation failed with observed count `0`; final `== 0` is green.
- Provider calls remain outside store transactions. The provider webhook is now deduplicated and, when an audit is relevant, appended through one atomic store operation.
- Authorization still updates activity only after an allowed action; session and audit mutate in the same transaction.
- `PostgresIdentityRepository` remains the existing SQL groundwork and is not wired as the application `IdentityStore`; extending its domain mapping is deferred to the SQL implementation task rather than invented in this port-refactor task.
- The legacy collection scan across `src`, focused unit/integration callers, and the contract has no matches.
