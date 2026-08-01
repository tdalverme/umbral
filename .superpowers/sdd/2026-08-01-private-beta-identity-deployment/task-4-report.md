# Task 4 report — identity persistence port

## Changed files

- `src/umbral/application/identity/ports.py`: replaced exposed mutable collections and lock with behavioral persistence operations.
- `src/umbral/application/identity/access.py`, `authorization.py`, `administration.py`, `retention.py`: callers use only the port and transactions.
- `src/umbral/infrastructure/db/repositories/identity.py`: made in-memory state private, with transaction rollback including provider-event dedupe and audit.
- `src/umbral/ops/identity.py`, `src/umbral/ops/smoke.py`: use narrow port queries rather than storage internals.
- `tests/contract/test_identity_store.py` and focused identity callers: behavioral conformance and migrated usages.

## RED / GREEN

RED was observed with `pytest tests/contract/test_identity_store.py`: all three tests failed because `save_invitation` and `append_provider_audit_once` did not exist.

GREEN was observed after the minimal adapter implementation: `3 passed` for the new store contract. The contract verifies save/load records, atomic webhook dedupe plus audit append, and state-plus-audit rollback.

`latest_attempt()` is a narrow dispatcher query: a caller can ask which attempt should be issued without seeing storage collection shape. `current_attempt()` cannot replace it because it intentionally sees only issued attempts; a pending attempt must be discovered by the job dispatcher. It is not a count/list/snapshot assertion helper.

## Verification

- `ruff check src/umbral/application/identity src/umbral/infrastructure/db/repositories/identity.py tests/contract/test_identity_store.py`: passed.
- `rg -n "store\.(invitations|users|links|roles|requests|attempts|sessions|audits|lock)" src/umbral/application/identity`: no matches.
- Focal contract: `3 passed`.
- Broader identity run: non-container slice reached 37 passing tests before legacy `test_magic_link_flow.py` caller migration. Docker-backed tests are blocked locally by denied access to `//./pipe/docker_engine`.

## Self-review / concerns

- Provider calls remain outside store transactions. The provider webhook is now deduplicated and, when an audit is relevant, appended through one atomic store operation.
- Authorization still updates activity only after an allowed action; session and audit mutate in the same transaction.
- `PostgresIdentityRepository` remains the existing SQL groundwork and is not wired as the application `IdentityStore`; extending its domain mapping is deferred to the SQL implementation task rather than invented in this port-refactor task.
- Remaining legacy callers in `tests/integration/identity/test_magic_link_flow.py` need the same save/query migration; no production identity application dictionary leaks remain.
