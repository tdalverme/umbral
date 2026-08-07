# Contract: Extraction v1

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Rules for producing `listing_observations` (UM-H3-005/006/007/008).
Machine-checkable definitions live at `contracts/criteria/v1/extraction-v1.json`
(input permitido, evidence schema, retry budget).

## Objective extraction (rules)

- Rules are pure, deterministic functions registered per concept key with
  golden cases (FR-010): `balcon`, `ambientes`, `piso`, `tipo_cocina`.
- Input fields (normalized listing): `description_text`, `location_text`,
  `amenities`, `property_type`, `rooms`, `floor`, `surface_m2`.
- Every observation carries fragment evidence:
  `{fragment: string|null, span: [start,end]|null, matched_on: [field]}`.
  Without a fragment the observation declares `"sin evidencia"` explicitly;
  it is never invented (FR-010).
- Running the same rule twice over the same listing produces identical
  observations (SC-004).

## Qualitative extraction (model)

- The model produces only the permitted schema of the concept: value +
  evidence + confidence; it never decides inclusion/exclusion of candidates,
  ranking or notifications (FR-011).
- **Input permitido**: deterministic projection of the normalized listing
  fields allowlisted in `extraction-v1.json`. Never PII of users, never raw
  HTML, never unlisted fields (FR-014).
- **Deployment posture**: external managed provider (clarification
  2026-08-06); the specific provider and costs are decided in the plan ADR;
  the domain only sees the `StructuredExtractor` port and a fake adapter for
  tests (R-06).
- **Schema conformance**: outputs are validated against the concept schema
  from the contract; invalid outputs (missing keys, wrong value types, out of
  bounds, no evidence) are rejected or retried with a bounded budget
  (`criteria.qualitative_max_attempts`, default 2); final failures persist as
  `failed` observations with `failure_code` and are queryable (FR-012).

## Versioning and lineage

- Every extraction artifact (rule, prompt, schema, model, embedding) is
  registered in `extraction_versions` as an immutable version (FR-013;
  UM-H3-008).
- Each observation references the exact `extraction_version_id` that produced
  it; the permitted input is reproducible by construction (projection +
  version) (SC-006).
- A new prompt/schema/model version invalidates only the observations
  referencing the previous version of that artifact (FR-015).

## Retry and failure rules

| Case | Behavior |
| --- | --- |
| invalid structured output | reject; retry up to `qualitative_max_attempts` |
| provider transient error | job-level transient failure (existing runtime retries) |
| provider permanent error | observation `failed` with `failure_code`; run records the count |
| no evidence in output | treated as invalid (no-evidence rejection) |

## P1 (deferred ordering)

- Embeddings: same permitted projection, kind=`embedding` versions
  (FR-018/FR-019).
- Urban context: external sources cached and rate-limited, per-signal
  source/date/geometry/algorithm (FR-020/FR-021).
