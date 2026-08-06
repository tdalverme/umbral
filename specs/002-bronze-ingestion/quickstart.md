# Quickstart: Bronze Ingestion

**Feature**: `002-bronze-ingestion` | **Date**: 2026-08-06

Runnable validation guide for the increment. Reference artifacts:
[data-model.md](./data-model.md), [import-contract-v1.md](./contracts/import-contract-v1.md),
[import-operations.md](./contracts/import-operations.md).

## Prerequisites

- Foundation runtime running (PostgreSQL, Redis, object storage) — see
  `docs/runbooks/runtime-local.md`.
- Operator product session available (identity increment, local fake identity
  boots an operator user for tests).
- Reference batch fixture:
  `tests/fixtures/imports/reference-batch.json` (12 records: 9 valid, 2
  invalid, 1 in-batch duplicate, 3 with a missing optional field).

## Validate the import contract (pure conformance)

```powershell
$env:PYTHONPATH = "src"
uv run pytest tests/unit/application/ingestion tests/contract/test_import_contract.py tests/unit/infrastructure/test_import_source.py tests/unit/api/test_imports.py -q
```

Expect: 100% of contract conformance cases pass — valid JSON/CSV accepted;
unsupported format/encoding/size/version rejected with actionable codes; each
invalid record quarantines without aborting the batch; operator authorization
is deny-by-default.

## Import a batch end to end (needs Docker/Postgres)

```powershell
uv run pytest tests/integration/ingestion tests/migrations/test_0003_ingestion.py
```

The in-memory slices (`test_idempotency.py`, `test_quality_report.py`) run
without Docker; the repository/capture/E2E slices use Testcontainers. Expect
the reference batch to produce:

- one `import_run` in state `succeeded` with `total_records=12`,
  `accepted=9`, `quarantined=2`, `duplicates=1`, `missing_fields=3`;
- 9 immutable `raw_listing_snapshots`, each with a verifiable `content_sha256`;
- 2 `quarantine_records` with code/rule/detail;
- the raw file as an immutable object version (`purpose=ingestion.raw_batch`)
  with matching SHA-256.

## Idempotency (US2)

```powershell
uv run pytest tests/integration/ingestion/test_idempotency.py
```

Expect: re-submitting the reference batch with the same `batch_key` returns the
existing run with zero new snapshots/effects; submitting identical content with
a different key creates a new run but zero duplicate `raw_listing_snapshots`;
an interrupted run retried with the same identity commits no duplicate rows.

## Operator entry and permissions (US1, SC-007, SC-008)

```powershell
uv run pytest tests/integration/identity/test_import_authorization.py tests/unit/api/test_imports.py
```

Expect:

- operator/administrator can submit, read runs and download quality;
- `user` role and anonymous requests are rejected (401/403) and audited;
- submitting a URL instead of a file is rejected (422/400) in 100% of cases.

## Migration checks

```powershell
uv run alembic current --check-heads
uv run alembic check
uv run pytest tests/migrations
```

Expect: `0003_bronze_ingestion` applies on empty and previous revision, single
head, no drift.

## Full harness

```powershell
.\scripts\check.ps1
```

Expect: all checks green, including the new imports surface and Spec Kit check.

## Manual smoke (local API)

1. Start the API and worker surfaces (see runtime-local runbook).
2. `POST /api/v1/imports/batches` with the reference batch, an operator session
   and `contract_version=1` → `202` with run id.
3. Poll `GET /api/v1/imports/runs/{run_id}` until `succeeded`.
4. `GET .../quality` and `GET .../quality/download` return matching counts.
5. Re-POST the same file without `batch_key` → same run returned, no new rows.
