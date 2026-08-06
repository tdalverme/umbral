# Controlled Import Contract v1

**Feature**: `002-bronze-ingestion` | **Status**: draft for controlled beta
source | **Ratifies**: UM-H0-009 (prerequisite)

This is the machine-checkable contract against which every batch is validated
(FR-004..FR-007). It targets the controlled beta: residential rental listings
in CABA. It will be ratified against the real controlled source before beta;
the loader is versioned so a later ratified revision swaps in without changing
domain code.

## Batch envelope

A batch is a single file, one of:

- **JSON**: an object with `contract_version` and `records`:

  ```json
  {
    "contract_version": "1",
    "records": [ { ...listing fields... } ]
  }
  ```

- **CSV**: UTF-8, comma-separated, single header row matching the field names
  below. `contract_version` is declared in the upload request, not the file.

The operator declares `source_id`, `source_version` and `contract_version` in
the upload request. The declared `contract_version` MUST be a supported value
(`"1"`), otherwise the batch is rejected.

## File-level rules (reject the whole batch)

| Rule | Value |
| --- | --- |
| Format | JSON object or CSV, as declared |
| Encoding | UTF-8 only |
| Max file size | 10 MiB |
| Structure | JSON must parse; CSV must have a header row and at least one record |
| Supported version | `contract_version == "1"` |

Rejection produces one actionable diagnostic naming the rule (e.g.
`file.format_unsupported`, `file.encoding_invalid`, `file.size_exceeded`,
`file.version_unsupported`). Zero records are processed (FR-005).

## Record-level rules (quarantine per record)

Required fields must be present and valid; violations quarantine the record
with a stable `code` and `rule`. Missing *optional* fields count toward
`missing_fields` in the quality report but do NOT quarantine.

| Field | Required | Type | Rules |
| --- | --- | --- | --- |
| `external_id` | yes | string | non-empty, max 500 |
| `operation` | yes | enum | `rental` only in v1 |
| `property_type` | yes | enum | `apartment`, `house`, `room`, `studio`, `commercial`, `other` |
| `price` | yes | number | > 0 |
| `currency` | yes | enum | `ARS`, `USD` |
| `expenses` | no | number | >= 0 |
| `address_text` | yes | string | non-empty, max 500 |
| `neighborhood` | no | string | max 200 |
| `latitude` / `longitude` | no | number | within CABA bounds when both present |
| `surface_m2` | no | number | > 0, <= 1_000_000 |
| `rooms` | no | integer | >= 0, <= 200 |
| `bedrooms` | no | integer | >= 0, <= 100 |
| `floor` | no | integer | >= -10, <= 1000 |
| `amenities` | no | array of string | each max 100; bounded list |
| `description` | no | string | max 20_000 |
| `media_urls` | no | array of string | each a valid http(s) URL; max 50 |
| `url` | no | string | valid http(s) URL |
| `published_at` | no | date/time | ISO 8601 |

Stable quarantine codes include:

- `contract.required_field` — a required field is absent/empty;
- `contract.type_invalid` — value does not match the declared type;
- `contract.enum_invalid` — value not in the allowed enum;
- `contract.range_invalid` — value outside the declared range;
- `contract.url_invalid` — media/URL field is not a valid http(s) URL;
- `record.duplicate` — identical `(source_id, external_id, content)` repeated
  in the same batch (counted, stored once, not quarantined).

A record with an invalid value in one field quarantines only that record; the
rest of the batch continues (FR-006, FR-007).

## Versioning

The contract is immutable once ratified. A changed contract publishes a new
minor (field additions) or major (breaking) revision; every run records the
`contract_version` and `parser_version` it used. No run's recorded version
changes retroactively.
