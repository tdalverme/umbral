# Data Model: Tools explicitas y permisos (H4.2)

**Feature**: 010-agent-tools | **Date**: 2026-08-09

Migration `0010_agent_tools` creates ONE new app-owned table
(`search_profile_update_proposals`) plus the `proposal_state` enum (R-03).
No new agent runtime tables: tool runs reuse `agent_node_runs` with
`node_kind='tool'` (discriminator already present in `0009`, R-10 of H4.1);
the LangGraph checkpoint tables stay library-managed and excluded from
Alembic (R-03 of H4.1). Entity conventions follow the codebase:
`IdentityAuditMixin` (id UUID, created_at, updated_at, version), Postgres
ENUMs named `<domain>_<state>` with `create_type=True`, constraint names
`uq_*`/`ck_*`/`ix_*`.

## Tables

### search_profile_update_proposals

Durable, auditable proposal to change a search profile (FR-008,
clarifications Q1/Q2). Created by `propose_search_profile_update`, consumed
exactly once by `apply_search_profile_update` (R-03/R-04/R-05).

| Field | Type | Notes |
| --- | --- | --- |
| id | UUID PK | mixin |
| session_id | UUID FK | `chat_sessions.id` — binding to the originating session (FR-008) |
| search_profile_id | UUID FK | `search_profiles.id` (H2.3) |
| base_profile_version | int | profile version the diff was built against (obsolescence, clarification Q1) |
| diff | JSONB | validated profile change (structured fields, no free text) |
| impact | JSONB | expected impact summary produced by propose (FR-007) |
| state | ENUM `proposal_state` | `pending` / `approved` / `rejected` |
| expires_at | datetime | proposal TTL; `AGENT_PROPOSAL_TTL_HOURS` (default 24, R-10) |
| applied_idempotency_key | string nullable | set on first apply; replay with same key returns the recorded result (R-05) |
| rejection_reason | string nullable | typed: `obsolete` / `expired` (only deterministic transitions, clarification Q2) |
| created_by | actor fields | mixin actor (user) |
| created_at / updated_at / version | mixin | version = optimistic lock |

Indexes:
- `ix_proposals_profile (search_profile_id, state)` — list/lookup per radar;
- `ix_proposals_session (session_id)` — lifecycle per session;
- partial unique `uq_proposals_profile_idempotency (search_profile_id,
  applied_idempotency_key) WHERE applied_idempotency_key IS NOT NULL` —
  DB-level one-use/replay guarantee (R-05, FR-012).

Validation rules (FR-008..FR-012):
- `diff` conforms to the profile fields contract (zones, budget, rooms,
  surface, criteria subset); validated by the same policy path used by
  `RadarService.update_profile` (R-04).
- `session_id` + `search_profile_id` must belong to the same user (search
  scope); every proposal lookup is scoped by user/session (FR-002).
- `state = pending` ⇒ `applied_idempotency_key IS NULL`; `state = approved`
  ⇒ `applied_idempotency_key NOT NULL` (applied exactly once, R-05).
- `state = rejected` ⇒ `rejection_reason IN ('obsolete','expired')`
  (deterministic transitions only, clarification Q2).
- Retention: kept while the account exists; deleted with the user
  (UM-H6-011 — out of scope here, policy recorded in FR-008).

### agent_node_runs (extended use, no schema change)

Tool invocations are recorded as rows with `node_kind='tool'` and
`node_name=<tool_name>` (R-01/R-14). The repository write path uses
`source="agent.tool"` following the existing `SqlAlchemyNodeRunRepository`
convention. Fields, enums and indexes unchanged from `0009`.

## State transitions

### Proposal lifecycle (deterministic only, clarification Q2)

```
pending → approved   (apply_search_profile_update with valid proposal,
                      explicit confirmation + idempotency key; profile
                      versioned, recomputation triggered, R-04)
pending → rejected   (only by:
                        - obsolescence: apply attempt when the current
                          profile version != base_profile_version
                          (ConcurrencyConflict), reason 'obsolete'
                        - expiration: maintenance duty marks pending with
                          expires_at past as rejected, reason 'expired',
                          R-11)
```

No interactive rejection and no editing in H4.2 (H4.3 owns
approve/edit/reject UX); 0 effects on the profile from rejected proposals
(FR-009).

## Contract JSON shapes (v2, additive to v1)

All under `contracts/agent/v2/` and `contracts/agent/tools/` (see
[contracts](./contracts/agent-tools-contracts-v1.md)). The v1 files remain
intact as the audited prior version (R-02).

### state-schema-v2.json

| Field | Kind | Delta vs v1 |
| --- | --- | --- |
| schema_version | integer | = 2 (R-02) |
| messages / context / intent / errors | unchanged | — |
| pending_action | nullable_object | may now reference a durable proposal (`{kind:"proposal", proposal_id}`) |
| tool_calls | list[tool_call] | NEW: `{tool, args}` pending calls of the turn |
| tool_results | list[tool_result] | NEW item shape: `{tool, status, result \| error_code}` (redacted) |

Validation: every value JSON-serializable (FR-005); `schema_version` must
match `AGENT_TOOLS_STATE_SCHEMA_VERSION` (2); checkpoints v1 are declared
incompatible with a typed `AgentStateIncompatible` error on resume (R-02).

### graph-topology-v2.json

| Node | Responsibility | Effect |
| --- | --- | --- |
| start | normalize input, init context | none |
| generate_reply | gateway structured output (reply-schema-v2); records model call | none |
| run_tools | executes pending `tool_calls` via the tool executor; records one `agent_node_runs` row per call (`node_kind='tool'`); writes redacted results/errors into `tool_results` | none (tools may persist via their services) |
| persist_reply | persist assistant message + close run | assistant message effect (ledger) |

Edges: `start → generate_reply`; `generate_reply → run_tools` (conditional:
`tool_calls` non-empty); `run_tools → generate_reply` (loop, bounded by
`AGENT_TOOLS_MAX_CALLS_PER_TURN` = 5); `generate_reply → persist_reply`
(conditional: no `tool_calls` left). `topology_version = 2`;
`tools: ["get_search_profile", "propose_search_profile_update",
"apply_search_profile_update", "find_matches", "explain_match",
"compare_listings", "record_feedback", "search_urban_context"]`.

### reply-schema-v2.json

| Field | Type | Validation |
| --- | --- | --- |
| reply_text | string | 1..2000 chars (unchanged) |
| refs | list[product_ref] | `{entity, id}` typed refs populated by tool results (R-13 of H4.1) |
| tool_calls | list[tool_call] | 0..`AGENT_TOOLS_MAX_CALLS_PER_TURN`; `{tool, args}` validated against the tool contract |

Invalid outputs are rejected or retried at most `AGENT_MODEL_MAX_RETRIES`
(2) times; 0 invalid content reaches state (FR-011).

### tool-contract-v1.json

Declares the 8 tools with the common contract (FR-001): `name`,
`description`, `mutating` (bool), `requires_confirmation` (bool), `timeout`,
`idempotent` (bool), `input_schema`, `output_schema`, `output_limits`
(max_items, forbidden_keys reuse from the events registry), `scope`
(always the session's search profile).

## Retention

- `search_profile_update_proposals`: kept while the account exists; deleted
  with the user (clarification Q1, FR-008). Expired proposals are marked
  `rejected('expired')` by the maintenance duty; rows are not deleted.
- Tool runs (`agent_node_runs` with `node_kind='tool'`): operational audit,
  same lifecycle as graph runs (H4.1).
