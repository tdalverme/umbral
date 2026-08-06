# Controlled Import Contract v1

**Status**: draft for controlled beta | **Source of truth**: `import-contract.json`

The machine-readable rules live in [import-contract.json](./import-contract.json).
This document explains them for operators. It targets the controlled beta:
residential rental listings in CABA.

## Batch envelope

A batch is a single file:

- **JSON**: an object with `contract_version` and `records`:

  ```json
  {
    "contract_version": "1",
    "records": [ { ...listing fields... } ]
  }
  ```

- **CSV**: UTF-8, comma-separated, single header row matching the field names.

The operator declares `source_id`, `source_version` and `contract_version` in
the upload request. The declared `contract_version` MUST be a supported value
(`"1"`).

## File-level rules (reject the whole batch)

| Rule | Value |
| --- | --- |
| Format | JSON object or CSV, as declared |
| Encoding | UTF-8 only |
| Max file size | 10 MiB |
| Max records | 10 000 |
| Structure | JSON must parse; CSV must have a header row |
| Supported version | `contract_version == "1"` |

Rejection produces one actionable diagnostic (`file.format_unsupported`,
`file.encoding_invalid`, `file.size_exceeded`, `file.version_unsupported`).
Zero records are processed.

## Record-level rules (quarantine per record)

Required fields must be present and valid; violations quarantine the record
with a stable `code`. Missing optional fields count toward `missing_fields` in
the quality report but do NOT quarantine.

| Field | Required | Type | Rules |
| --- | --- | --- | --- |
| `external_id` | yes | string | 1..500 |
| `operation` | yes | enum | `rental` in v1 |
| `property_type` | yes | enum | apartment/house/room/studio/commercial/other |
| `price` | yes | number | > 0 |
| `currency` | yes | enum | `ARS`, `USD` |
| `expenses` | no | number | >= 0 |
| `address_text` | yes | string | 1..500 |
| `neighborhood` | no | string | <= 200 |
| `latitude` / `longitude` | no | number | CABA bounds when present |
| `surface_m2` | no | number | (0, 1_000_000] |
| `rooms` | no | integer | 0..200 |
| `bedrooms` | no | integer | 0..100 |
| `floor` | no | integer | -10..1000 |
| `amenities` | no | array | <= 100 strings, each <= 100 |
| `description` | no | string | <= 20 000 |
| `media_urls` | no | array | <= 50 http(s) URLs |
| `url` | no | string | http(s) URL |
| `published_at` | no | date/time | ISO 8601 |

Stable quarantine codes:

- `contract.required_field` — a required field is absent/empty;
- `contract.type_invalid` — value does not match the declared type;
- `contract.enum_invalid` — value not in the allowed enum;
- `contract.range_invalid` — value outside the declared range;
- `contract.url_invalid` — media/URL field is not a valid http(s) URL;
- `source.parse_error` — the record could not be parsed from the file.

A record that is identical to one already captured for the same source and
`external_id` is counted as a duplicate and stored once, never quarantined.

## Versioning

The contract is immutable once ratified. A changed contract publishes a new
revision; every run records the `contract_version` it used. No run's recorded
version changes retroactively.
