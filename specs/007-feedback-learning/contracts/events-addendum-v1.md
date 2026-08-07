# Contract: Product Events v1 — Addendum (Feedback y aprendizaje)

**Feature**: `007-feedback-learning` | **Date**: 2026-08-07

Additive additions to the closed events registry
(`contracts/events/v1/events-registry.json`). No existing event is modified;
payloads carry ids/state/counts only — never free-feedback text, reason labels,
evidence or listing text (FR-016/FR-018, SC-008, R-13).

## New event types

| event_type | version | emitter | when | payload |
| --- | --- | --- | --- | --- |
| `feedback.recorded.v1` | 1 | server | a feedback event is recorded (new, superseding or no-op) | `event_id`, `search_profile_id`, `listing_id`, `event_type`, `decision_state`, `superseded` (bool), `reason_count`, `has_free_feedback` (bool, P1) |
| `learning.proposal_created.v1` | 1 | server | a pending proposal is created | `proposal_id`, `search_profile_id`, `concept_key`, `polarity`, `evidence_count`, `policy_version` |
| `learning.proposal_confirmed.v1` | 1 | server | a proposal is confirmed and applied | `proposal_id`, `search_profile_id`, `concept_key`, `applied_profile_version`, `run_id` |
| `learning.proposal_rejected.v1` | 1 | server | a proposal is rejected | `proposal_id`, `search_profile_id` |
| `learning.proposal_expanded.v1` | 1 | server | a pending proposal is edited (expand) | `proposal_id`, `search_profile_id` |
| `learning.proposal_undone.v1` | 1 | server | a confirmed proposal is undone | `proposal_id`, `search_profile_id`, `run_id` |
| `learning.proposal_expired.v1` | 1 | server | a pending proposal transitions to expired (lazy) | `proposal_id`, `search_profile_id` |
| `feedback.shortlist_viewed.v1` | 1 | client (web) | a user views the shortlist | `search_profile_id`, `item_count` |
| `feedback.dismissed_viewed.v1` | 1 | client (web) | a user views the dismissed list | `search_profile_id`, `item_count` |

## Unchanged events reused by this increment

| event_type | emitter | when |
| --- | --- | --- |
| `recommendation.run_published.v1` | server | a run publishes after a confirmed learning change (existing payload; trigger remains `edited`) |
| `criteria.compilation_created.v1` | server | compilation created by the confirm/undo flow (existing payload) |
| `recommendation.impression.v1` / `recommendation.detail_viewed.v1` | client | radar exploration (existing; unchanged) |

The registry conformance test is extended with the nine new types.
