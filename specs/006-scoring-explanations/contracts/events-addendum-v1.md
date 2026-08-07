# Contract: Product Events v1 — Addendum (Scoring and Explanations)

**Feature**: `006-scoring-explanations` | **Date**: 2026-08-07

Additive additions to the closed events registry
(`contracts/events/v1/events-registry.json`). No existing event is modified;
payloads carry ids/versions/counts only — never evaluation values, evidence,
fragments or listing text (FR-021, SC-010, R-11).

## New event types

| event_type | version | emitter | when | payload |
| --- | --- | --- | --- | --- |
| `recommendation.explanation_viewed.v1` | 1 | client (web) | a user views an explanation (card reasons or detail breakdown) | `search_profile_id`, `run_id`, `listing_id`, `score_version` |
| `recommendation.comparison_viewed.v1` | 1 | client (web) | a user views a comparison matrix | `search_profile_id`, `run_id`, `listing_count`, `score_version` |

## Unchanged events reused by this increment

| event_type | emitter | when |
| --- | --- | --- |
| `recommendation.run_published.v1` | server (run job) | a v1 run publishes items and evaluations atomically (existing payload; `score_policy_version` now may be `scoring-policy-v1`) |
| `recommendation.impression.v1` / `recommendation.detail_viewed.v1` | client | radar exploration (existing; unchanged) |

Run creation/editing triggers and the events registry contract remain as
H2.3/H3.1; the registry conformance test is extended with the two new types.
