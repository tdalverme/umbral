# Import Operations Contract (Operator Entry)

**Feature**: `002-bronze-ingestion` | **Date**: 2026-08-06

HTTP contract for the operator entry (UM-H2-003). Operations sit below
`/api/v1` and require a product session with the `operator` or `administrator`
role (deny-by-default; actions registered in `domain/identity/policy.py`).
Errors follow the existing `application/problem+json` contract with typed
`code` values and correlation headers.

## Authorization actions

| Action | Allowed roles |
| --- | --- |
| `ops.ingestion.batch.submit` | operator, administrator |
| `ops.ingestion.run.read` | operator, administrator |
| `ops.ingestion.quality.read` | operator, administrator |

## Endpoints

### POST /api/v1/imports/batches

Submit a controlled batch. `multipart/form-data` with file upload only — URLs
are never accepted (FR-021).

Request fields:

| Field | Type | Rules |
| --- | --- | --- |
| `file` | binary | required; CSV or JSON, UTF-8, <= 10 MiB |
| `source_id` | string | required, normalized |
| `source_version` | string | required |
| `contract_version` | string | required; must be `"1"` |
| `batch_key` | string | optional; when absent derived as SHA-256 of file |

Responses:

- `202 Accepted` — run created (or existing run returned if the identity is a
  replay); body is the run snapshot.
- `400` — file/format/size/version rejected with an actionable diagnostic.
- `401` / `403` — missing or unauthorized session.
- `422` — malformed multipart.

### GET /api/v1/imports/runs/{run_id}

Progress and result of one run. Returns `state`, `created_at`, `finished_at`,
`error_code`/`error_detail`, and the derived counts (`total_records`,
`accepted`, `quarantined`, `duplicates`, `missing_fields`).

- `200` — run snapshot.
- `404` — unknown run.
- `401` / `403` — unauthorized.

### GET /api/v1/imports/runs/{run_id}/quality

Quality summary for a succeeded run:

```json
{
  "run_id": "...",
  "state": "succeeded",
  "counts": { "total": 12, "accepted": 9, "quarantined": 2, "duplicates": 1, "missing_fields": 3 },
  "missing_fields_by_name": { "neighborhood": 2, "expenses": 1 },
  "abnormal_distributions": [
    { "field": "price", "signal": "outlier", "detail": "2 values exceed 3 IQR" }
  ]
}
```

- `200` — summary derived from committed rows (always matches real counts).
- `409` — run not in a terminal state.
- `401` / `403` / `404` — as above.

### GET /api/v1/imports/runs/{run_id}/quality/download

CSV of per-record quarantine detail (`run_id`, `source_id`, `external_id`,
`code`, `rule`, `detail`). Content type `text/csv; charset=utf-8`; `Cache-Control:
no-store`; operator authorization required (FR-018).

### GET /api/v1/imports/quarantine/{record_id}

Detail of one quarantine record (code, rule, detail, bounded payload). Requires
`ops.ingestion.run.read`.

## Contract versioning

The OpenAPI document at `contracts/openapi/v1/openapi.json` is the published
contract; these operations are exported deterministically and covered by the
existing `check-contracts` and generated-client drift checks.
