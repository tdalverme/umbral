# Contract: Feedback v1 — Events, states and quick reasons

**Feature**: `007-feedback-learning` | **Date**: 2026-08-07

Ratifies the machine-checkable files
`contracts/feedback/v1/feedback-events.json` (event + decision-state shape and
endpoints) and `contracts/feedback/v1/quick-reasons-v1.json` (curated reason
seed). Rules below bind the API and the service.

## Event model

| Field | Rules |
| --- | --- |
| event_type | `like` \| `dislike` \| `save` \| `dismiss` \| `contacted` (FR-001) |
| actor / context | profile (search) + listing; run optional when the action targets a scored item |
| reasons | optional; keys MUST exist in `quick-reasons-v1.json` and be allowed for the event_type; polarity from the registry (FR-006) |
| free_feedback | P1; optional text of a like/dislike, <= 500 chars; NEVER in events/analytics (FR-016) |
| idempotency_key | required; replay returns the existing event without duplication (FR-003) |
| immutability | events are append-only; 0 mutations (FR-002) |

## Decision state and compensation

- The current decision state per (profile, listing) is the last active event.
- Changing a decision supersedes the active event (compensation link) and
  inserts a new one in the same transaction (FR-004).
- Repeating the currently active action is an idempotent no-op.
- `contacted` is terminal: once active, further feedback on the listing is
  rejected with `feedback_terminal`; no undo (FR-005).

## Quick reasons v1 (seed)

`quick-reasons-v1.json`: `{contract_version, registry_version, reasons:
[{key, label, polarity, concept_key?, allowed_on[]}]}`. Initial curated set
(keys fixed; labels reviewed with product per UM-H0-007):

| key | polarity | concept_key | allowed_on |
| --- | --- | --- | --- |
| price_too_high | negative | precio | dislike, dismiss |
| price_fits | positive | precio | like, save |
| expensas_high | negative | expensas | dislike, dismiss |
| location_no | negative | ubicacion | dislike, dismiss |
| location_yes | positive | ubicacion | like, save |
| rooms_wrong | negative | ambientes | dislike, dismiss |
| surface_wrong | negative | superficie | dislike, dismiss |
| building_state | negative | estado_general | dislike, dismiss |
| access_ok | positive | acceso_transporte | like, save |
| other | n/a | null | all |

Unknown keys or keys not allowed for the event_type are rejected with
`feedback_invalid_reason` at record time.

## Endpoints

| Endpoint | Purpose | Typed errors |
| --- | --- | --- |
| `POST /api/v1/search-profiles/{id}/feedback` | record an action; returns event + decision state | `feedback_not_found`, `feedback_terminal`, `feedback_invalid_reason`, `feedback_conflict`, ownership 403 |
| `GET /api/v1/search-profiles/{id}/decision-items?decision_state=&page_size=&after_position=` | saved/dismissed/liked/disliked/contacted views (drives shortlist + dismissed screens; UM-H3-026) | ownership 403, invalid state 400 |
| `GET /api/v1/search-profiles/{id}/matches?include_dismissed=false` | additive param + `decision_state` annotation per item; dismissed hidden by default (FR-008) | unchanged + ownership |

All endpoints are deny-by-default (`product.feedback.write`,
`product.feedback.read`); pagination follows the position-cursor convention.
