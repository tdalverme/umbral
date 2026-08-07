# Contract: Learning Policy v1 and Proposals

**Feature**: `007-feedback-learning` | **Date**: 2026-08-07

Ratifies `contracts/learning/v1/learning-policy-v1.json` (versioned rule seed)
and binds the proposal lifecycle. Mirrors the scoring policy contract of H3.2
(R-05).

## Policy document v1

| Field | Meaning | Default (seed `learning-v1`) |
| --- | --- | --- |
| `min_signals` | minimum consistent reasoned like/dislike events on the same concept (same polarity) required to propose | 3 |
| `window_days` | lookback window for signal counting | 90 |
| `min_signal_confidence` | minimum signal confidence; reasoned actions are 1.0 by construction (R-04) | 1.0 |
| `cooldown_days` | no new proposal for (profile, concept) after the last pending/confirmed proposal on it | 7 |
| `proposal_expiration_days` | pending proposal lifetime before lazy expiry | 30 |
| `default_suggested_weight` | initial `suggested_weight` of a proposal (editable via expand) | 0.3 |
| `default_suggested_confidence` | initial `suggested_confidence` of a proposal (editable via expand) | 0.6 |

The policy is immutable and versioned; each change appends a new version
without mutating previous ones; every proposal records the version that
created it (FR-009).

## Signals

- A signal is an active reasoned like (positive) or dislike (negative) event
  whose reason is linked to a concept (clarification 2026-08-07; FR-009).
- Save, dismiss and contacted never generate proposals (they record state and
  evidence only).
- The engine is pure and deterministic; 0 LLM in the decision (FR-009).

## Proposal

| Field | Rules |
| --- | --- |
| scope | one search profile (per search); 0 global changes (FR-010) |
| kind | `preference_fact` in v1 (polarity, suggested_weight, suggested_confidence, value null); `criterion` reserved, not produced in v1 (R-06) |
| evidence_refs | ids of the feedback events that justify the proposal |
| states | pending \| confirmed \| rejected \| expired \| superseded |
| expiry | lazy; confirm on expired rejects with `proposal_expired` (R-09) |
| cooldown | one pending proposal per (profile, concept) at a time; no re-proposal inside cooldown (FR-011) |

## Lifecycle

```text
pending --confirm--> confirmed  (fact -> bump version -> compile -> run "edited")
pending --reject---> rejected
pending --(time)----> expired   (lazy)
pending --expand---> pending    (edit change payload, diff shown)
confirmed --undo---> superseded (compensating fact + new run; intermediate run kept)
```

- Confirm applies the proposal as a preference fact
  (`fact_source="learning.proposal"`), versions the profile, compiles and
  submits a new run; the previous run stays consultable (FR-012/FR-014).
- Undo records a compensating fact with the pre-confirmation values and runs
  the same sequence (FR-012).
- 0 escalations to hard filter happen automatically (FR-010); a proposal is
  never applied without explicit confirmation.

## Endpoints

| Endpoint | Purpose | Typed errors |
| --- | --- | --- |
| `GET /search-profiles/{id}/learning-proposals?state=` | pending list + history (drives the radar banner; FR-013) | ownership 403 |
| `PUT /search-profiles/{id}/learning-proposals/{pid}` | expand: edit pending change payload | `proposal_not_found`, `proposal_not_pending`, `feedback_invalid_reason`, 400 |
| `POST /search-profiles/{id}/learning-proposals/{pid}/confirm` | apply + re-run | `proposal_not_pending`, `proposal_expired`, `proposal_not_found`, 409 concurrency |
| `POST /search-profiles/{id}/learning-proposals/{pid}/reject` | mark rejected | `proposal_not_pending`, `proposal_not_found` |
| `POST /search-profiles/{id}/learning-proposals/{pid}/undo` | revert a confirmed proposal | `proposal_not_confirmed`, `proposal_not_found` |

All endpoints are deny-by-default (`product.learning.read` / `.write`).
