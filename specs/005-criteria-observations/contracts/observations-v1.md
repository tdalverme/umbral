# Contract: Listing Observations v1

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Identity, states and lineage of `listing_observations` (UM-H3-005; FR-009).
Machine-checkable definitions live at `contracts/criteria/v1/observations-v1.json`.

## Identity

- At most **one active observation per (listing, concept, source)**
  (clarification 2026-08-06; SC-012), enforced by the partial unique index
  `uq_listing_observations_active`.
- Previous versions are preserved as history; recompute replaces the active
  one (supersede) and never leaves two active rows.

## Observation shape

| Field | Rules |
| --- | --- |
| `listing_id` | FK `silver_listings.id` |
| `concept_key` | must exist in the registry |
| `matcher_type` | from matcher-types-v1 |
| `value` | JSONB per concept schema |
| `score` | 0..1 |
| `confidence` | 0..1 |
| `evidence` | `{fragment, span, matched_on}` (see extraction-v1) |
| `source` | `rule` \| `model` |
| `extraction_version_id` | exact lineage (FR-013) |
| `state` | `active` \| `invalidated` \| `superseded` \| `failed` |
| `failure_code` | required when `failed` |

## State semantics

| State | Meaning | Usable in new results |
| --- | --- | --- |
| `active` | current valid observation | yes |
| `invalidated` | affected by a version change, awaiting recompute | never (FR-017) |
| `superseded` | replaced by a newer observation | no (audit only) |
| `failed` | rejected after bounded retries | no (audit only; FR-012) |

## Transitions

- `active -> invalidated`: automatic when a version change (concept,
  extraction artifact, parser) affects the observation (FR-015).
- `invalidated -> superseded`: when a recompute publishes the replacement in
  the same transaction (FR-016).
- `active -> superseded`: direct replacement by a recompute (e.g. scope
  recompute without prior invalidation window).
- New extraction insert: new `active` row; the partial unique index rejects
  duplicates.

## Lineage

observation -> `extraction_versions` (rule/prompt/schema/model) ->
`silver_listings` (`normalizer_version`, `snapshot_id`) -> Bronze snapshot.
The walk is queryable for 100% of observations (SC-006).
