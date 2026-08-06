# Contract: Product Events v1

**Feature**: `004-structured-search-radar` | **Date**: 2026-08-06

Minimal versioned dictionary of product events emitted by the radar increment
(UM-H2-033; seed for the full dictionary UM-H0-013). The registry is closed:
every event type declares its allowed payload keys, and sensitive keys are
forbidden. Events are persisted in `product_events` and never contain PII
beyond the actor id already known to the system (FR-020, SC-007).

## Event types (v1)

| Event | Emitted by | When |
| --- | --- | --- |
| `radar.created.v1` | server (create path) | a search profile is created |
| `recommendation.run_published.v1` | server (run job) | a run reaches `succeeded` and its items become the visible results |
| `recommendation.impression.v1` | client (BFF) | a match card is rendered in the radar list |
| `recommendation.detail_viewed.v1` | client (BFF) | the user opens a match detail |
| `listing.source_opened.v1` | client (BFF) | the user opens the original source URL |

## Payload schema (per type)

| Event | Required keys | Forbidden |
| --- | --- | --- |
| `radar.created.v1` | `search_profile_id`, `profile_version` | — |
| `recommendation.run_published.v1` | `search_profile_id`, `run_id`, `candidate_count`, `published_item_count`, `score_policy_version` | — |
| `recommendation.impression.v1` | `search_profile_id`, `run_id`, `listing_id` | — |
| `recommendation.detail_viewed.v1` | `search_profile_id`, `run_id`, `listing_id` | — |
| `listing.source_opened.v1` | `search_profile_id`, `run_id`, `listing_id`, `source_id` | `url` (never echo full URLs) |

## Common fields (server-assigned)

`event_id`, `event_type`, `event_version`, `occurred_at`, `actor_id`,
`correlation_id`, `payload`. All timestamps UTC; payloads are bounded JSON
objects; unknown keys are rejected.

## Validation rules

- Event type must exist in the registry; unknown types are rejected (400).
- Required keys per type; extra keys rejected (`extra="forbid"` semantics).
- Forbidden keys (PII candidates) are rejected even if a type allows other
  keys: `email`, `phone`, `name`, `url`, `ip`, `token`, `password`,
  `description_text`, `location_text`, `geometry`.
- Client-emitted events are authenticated (session required) and authorized to
  the owning profile of the `search_profile_id` they reference; a
  `search_profile_id` or `listing_id` that does not belong to the actor is
  rejected (403).

## Persistence

One row per event in `product_events` with `occurred_at`, actor, correlation
and the validated payload. Server events are written in the same transaction
as the domain change they record (create profile; publish run). Client events
are written by the event endpoint after validation.
