# Data Model: Comportamiento conversacional y UI (H4.3)

**Feature**: 011-conversational-ui | **Date**: 2026-08-10

Migration `0011_chat_streaming` alters TWO existing app-owned tables:
`chat_messages` (idempotent send, R-06) and
`search_profile_update_proposals` (interactive transitions + edit chain,
R-05). No new tables. LangGraph checkpoint tables stay library-managed and
excluded from Alembic (R-03 of H4.1). Entity conventions follow the
codebase: `IdentityAuditMixin`, Postgres ENUMs `<domain>_<state>` with
`create_type=True`, constraint names `uq_*`/`ck_*`/`ix_*`.

## Tables

### chat_messages (extended)

| Field | Type | Delta | Notes |
| --- | --- | --- | --- |
| (existing fields) | — | — | id, session_id FK, role, content JSONB, state, graph_run_id, correlation_id, actor/audit mixin (H4.1) |
| client_message_id | UUID nullable | NEW | idempotency key of the send (client-generated, R-06) |

Indexes:
- partial unique `uq_chat_messages_session_client (session_id,
  client_message_id) WHERE client_message_id IS NOT NULL` — replay with the
  same key returns the recorded message, 0 duplicates and 0 new runs
  (FR-024, R-06).

Validation: `client_message_id` nullable (sends without it keep current
behavior); content kinds unchanged (text/reply, H4.1) with optional
`context: {entity, id}` on user messages for the contextual entry
(UM-H4-025, R-08).

### search_profile_update_proposals (extended)

| Field | Type | Delta | Notes |
| --- | --- | --- | --- |
| (existing fields) | — | — | id, session_id FK, search_profile_id FK, base_profile_version, diff JSONB, impact JSONB, state, expires_at, applied_idempotency_key, rejection_reason, created_by/audit mixin (H4.2) |
| rejection_note | string nullable | NEW | user's own bounded note on interactive rejection (max 200 chars); never in events, redacted outputs or logs beyond the row (R-05) |
| superseded_by_proposal_id | UUID FK self nullable | NEW | edit chain: original `rejected('edited')` links to the derived proposal (R-05) |

Indexes:
- `ix_proposals_superseded_by (superseded_by_proposal_id)` — follow the
  edit chain for audit.

Validation rules (extended on H4.2):
- `rejection_reason` domain extends to
  `{obsolete, expired, user, edited}` (R-05). If the DB column is
  constrained (check/enum) at implementation time, the migration widens it;
  plain-string columns need no DDL.
- `state = rejected` ⇒ `rejection_reason IS NOT NULL`; reason `user`
  requires the interactive reject path (0 effects on the profile, FR-013);
  reason `edited` requires `superseded_by_proposal_id` pointing to a
  pending derived proposal (FR-014, clarification Q2).
- A derived proposal inherits the base profile version of its parent and
  its own `expires_at` (new TTL window); single-use applies to each
  proposal independently.
- 0 mutation of the original proposal on edit: the diff of the original row
  is never rewritten (0 reescrituras, clarification Q2).

## State transitions

### Proposal lifecycle (H4.3 extends the deterministic H4.2 lifecycle)

```
pending → approved   (apply via decision approve on the same checkpoint:
                      confirmation + idempotency key; profile versioned,
                      recomputation triggered; R-04)
pending → rejected   (by:
                        - obsolescence: apply attempt on a stale base
                          version, reason 'obsolete' (H4.2)
                        - expiration: maintenance duty, reason 'expired'
                          (H4.2)
                        - interactive reject: decision reject, reason
                          'user' + optional rejection_note (FR-013, R-05)
                        - edit: decision edit derives a new proposal,
                          reason 'edited' + superseded_by_proposal_id
                          (FR-014, clarification Q2, R-05))
pending (derived) → pending→approved/rejected  (same lifecycle; the edit
                          chain stays fully auditable)
```

Interactive rejection and editing are H4.3 (H4.2 was deterministic-only);
every transition is recorded in the row + the resuming run (R-16).

### Chat session / message lifecycle (unchanged from H4.1)

`active` sessions accept turns; `paused`/`archived` reject sends with typed
error and keep history recoverable. Messages are immutable once created.
Run statuses include `interrupted` (waiting for a HITL decision) and remain
claimable per session (`_NON_TERMINAL`, H4.1).

## Checkpoint state (operational, NOT product truth)

The LangGraph checkpoint (thread = run) holds the v3 state shape
(see `contracts/agent/v3/state-schema-v3.json`):

- `intent` — compiled intent + parameters + confidence of the turn
  (R-01/R-02).
- `clarification` — `{pending_params, rounds}` of the clarification loop
  (R-03).
- `pending_action` — `{kind: "proposal", proposal_id}` set before the HITL
  interrupt; used for the run↔proposal cross-check on decision (R-04).
- `interrupt` payload — the tipified proposal decision waiting for the
  user (type, proposal_id, diff, impact, expires_at).

Checkpoints never replace proposals, messages, runs or events as product
truth (principle I); the waiting window for a decision equals the proposal
TTL (`AGENT_PROPOSAL_TTL_HOURS`, H4.2).

## Retention

- `chat_messages` + `chat_sessions`: kept while the account exists (H4.1);
  the new `client_message_id` column follows the same lifecycle.
- `search_profile_update_proposals`: kept while the account exists; the
  edit chain (`superseded_by_proposal_id`) is preserved as audit (R-05).
- Checkpoints: short inactivity window, purged by the existing duty
  (H4.1), 0 impact on persisted history.
