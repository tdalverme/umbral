# Contract: Product Events v1 — Addendum (criteria)

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Additive event types for the closed registry `contracts/events/v1` (R-09).
The registry remains closed: unknown types, missing keys, forbidden PII keys
and extra keys are rejected. Existing v1 types are unchanged (non-breaking,
OpenAPI/registry major stays 1).

## New event types (server-emitted)

| Event | When | Required keys |
| --- | --- | --- |
| `criteria.concept_version_created.v1` | a concept is registered or edited (same transaction as the new `concept_versions` row) | `concept_key`, `concept_version` |
| `criteria.compilation_created.v1` | a criteria compilation is persisted | `profile_id`, `profile_version`, `compilation_version`, `criterion_count`, `warning_count` |
| `criteria.observation_batch_published.v1` | an extraction/recompute batch publishes observations | `scope_kind`, `scope_key`, `extraction_version_id`, `published_count`, `superseded_count`, `failed_count` |
| `criteria.recompute_completed.v1` | a recomputation run reaches a terminal state | `recompute_run_id`, `scope_kind`, `scope_key`, `cause`, `state`, `published_count`, `failed_count` |

## Common rules (inherited from v1)

- Common fields: `event_id`, `event_type`, `event_version`, `occurred_at`,
  `actor_id`, `correlation_id`, `payload`; UTC timestamps; bounded JSON
  payloads; unknown keys rejected.
- Forbidden keys inherited and enforced for these types: `email`, `phone`,
  `name`, `url`, `ip`, `token`, `password`, `description_text`,
  `location_text`, `geometry`, `value`, `fragment` — event payloads carry ids,
  versions and counts only; never observation values, evidence fragments or
  text (SC-010).
- Server events are written in the same transaction as the domain change they
  record (concept version, compilation, batch publication, recompute
  completion).

## Persistence

One row per event in `product_events` (existing table, unchanged schema).
