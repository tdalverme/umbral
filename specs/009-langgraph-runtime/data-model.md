# Data Model: Runtime LangGraph (H4.1)

**Feature**: 009-langgraph-runtime | **Date**: 2026-08-09

Migration `0009_langgraph_runtime` creates five tables owned by the app and
does NOT touch the LangGraph checkpoint tables (R-03). Entity conventions
follow the existing codebase: `IdentityAuditMixin` (id UUID, created_at,
updated_at, version), Postgres ENUMs named `<domain>_<state>` with
`create_type=True`, constraint names `uq_*`/`ck_*`/`ix_*`.

## Tables

### chat_sessions

Session is a durable product object linking a user and a search profile
(FR-001). Status mirrors the search profile state (R-12): the application
derives it; no own transitions are stored.

| Field | Type | Notes |
| --- | --- | --- |
| id | UUID PK | mixin |
| user_id | UUID FK | owner; every lookup is scoped by it |
| search_profile_id | UUID FK | `search_profiles.id` (H2.3) |
| status | ENUM `chat_session_state` | `active` / `paused` / `archived`; derived from profile status |
| created_at / updated_at / version | mixin | version = optimistic lock |

Indexes: `ix_chat_sessions_user_status (user_id, status)`,
`ix_chat_sessions_profile (search_profile_id)`.

Validation: `user_id` and `search_profile_id` NOT NULL; unique
`(user_id, search_profile_id)` is NOT enforced — a user may hold several
sessions per radar (assumption). Versioned via `version_id_col`.

### chat_messages

Immutable message with role, typed allowed content and lineage to the graph
run that produced it (FR-002, FR-003).

| Field | Type | Notes |
| --- | --- | --- |
| id | UUID PK | mixin |
| session_id | UUID FK | `chat_sessions.id` |
| role | ENUM `chat_message_role` | `user` / `assistant` / `system` |
| content | JSONB | typed allowed content (see MessageContent below) |
| state | ENUM `chat_message_state` | `complete` (only state in v1; partial never persisted, R-11) |
| graph_run_id | UUID FK nullable | `agent_graph_runs.id` lineage (assistant/system only) |
| created_at | mixin | updated_at/version present but unused for appends |

Indexes: `ix_chat_messages_session_created (session_id, created_at)`.

Validation rules:
- IMMUTABLE: no UPDATE path in the repository; only INSERT (FR-002).
- `content` must conform to the allowed content contract: `{kind: "text", text: string}` or `{kind: "ref", ref: {entity: string, id: string}}`; text length ≤ `CHAT_MESSAGE_MAX_LENGTH` (default 4000, FR-003); no HTML/media.
- `role = user` ⇒ `graph_run_id` NULL (input messages exist before the run); `role = assistant` ⇒ `graph_run_id` NOT NULL.
- `state = complete` always in v1 (R-11).

### agent_graph_runs

One row per graph run; resume increments `attempt` on the same row
(R-06). Version/latency/status/errors/usage/correlation per FR-016.

| Field | Type | Notes |
| --- | --- | --- |
| id | UUID PK | also the LangGraph thread id |
| session_id | UUID FK | `chat_sessions.id` |
| state_schema_version | int | from `AGENT_STATE_SCHEMA_VERSION` / state-schema contract |
| topology_version | int | from `AGENT_GRAPH_TOPOLOGY_VERSION` / graph-topology contract |
| status | ENUM `agent_run_state` | `pending` / `running` / `completed` / `failed` / `interrupted` (spec states) |
| attempt | int | 1 on first run; +1 per resume |
| started_at / finished_at | datetime | latency = finished_at - started_at |
| error_summary | JSONB nullable | typed error code + message (no conversation content, FR-018) |
| token_usage | JSONB nullable | input/output/total tokens (FR-016) |
| correlation_id | UUID | joins runs/nodes/model calls |
| created_at / updated_at / version | mixin | |

Constraints: partial unique index
`uq_agent_graph_runs_session_active ON (session_id) WHERE status IN ('pending','running','interrupted')`
— the DB-level 0-parallel guarantee (FR-015, R-06); an interrupted run must be
resumed before any new turn (there is no cancel path in H4.1). Indexes:
`ix_agent_graph_runs_session (session_id, created_at)`,
`ix_agent_graph_runs_correlation (correlation_id)`.

### agent_node_runs

Node (and later tool) executions inside a run (FR-017, R-10).

| Field | Type | Notes |
| --- | --- | --- |
| id | UUID PK | mixin |
| graph_run_id | UUID FK | `agent_graph_runs.id` |
| node_name | string | e.g. `start`, `generate_reply`, `persist_reply` |
| node_kind | ENUM `agent_node_kind` | `node` / `tool` (tool rows arrive in H4.2) |
| status | ENUM `agent_run_state` | same enum as graph runs |
| started_at / finished_at | datetime | latency |
| error_summary | JSONB nullable | FR-018 |
| usage | JSONB nullable | token usage when the node called the model |
| correlation_id | UUID | same as graph run |

Index: `ix_agent_node_runs_run (graph_run_id, started_at)`.

### agent_model_calls

Every model call with versions and usage (FR-012, FR-018).

| Field | Type | Notes |
| --- | --- | --- |
| id | UUID PK | mixin |
| graph_run_id | UUID FK nullable | NULL only for harness-only calls |
| model_version | string | immutable per call |
| prompt_version | string | immutable per call |
| schema_version | string | reply-schema version used |
| status | ENUM `agent_call_state` | `success` / `invalid_output` / `timeout` / `error` / `retried` |
| input_tokens / output_tokens / total_tokens | int | usage |
| latency_ms | int | |
| error_code | string nullable | typed, no PII |
| correlation_id | UUID | |

Indexes: `ix_agent_model_calls_run (graph_run_id)`,
`ix_agent_model_calls_correlation (correlation_id)`.

## State transitions

### Session status (derived, R-12)

```
search_profiles.status          chat_sessions.status (derived)
active                  →       active
paused                  →       paused        (new turns rejected)
archived                →       archived      (new turns rejected)
```
No stored transitions; the service mirrors the profile state on read and
rejects new turns when not active.

### Graph run lifecycle

```
pending → running → completed
        ↘ running → failed     (model/network error)
        ↘ running → interrupted (disconnect/timeout mid-execution)
interrupted → running (resume, attempt+1) → completed/failed/interrupted
```
Non-terminal states (`pending`, `running`, `interrupted`) block new turns via
the partial unique index (R-06): an interrupted run must be resumed
(`attempt+1`), and there is no cancel path in H4.1 (H4.3 adds it). A `failed`
run is terminal: a new message starts a fresh run.

## Contract JSON shapes

All under `contracts/agent/v1/` (see [contracts](./contracts/agent-contracts-v1.md)).

### state-schema-v1.json

Declares the v1 checkpointed state fields (FR-004) and the serializable
guarantee (FR-005):

| Field | Kind | Notes |
| --- | --- | --- |
| schema_version | integer | = 1; recorded in every checkpoint (FR-004) |
| messages | list[chat_message] | turn messages (also mirrored in `chat_messages` for history) |
| context | object | serializable dict; `effects_applied` ledger lives here (R-04) |
| intent | object \| null | v1: always null (intent compilation is H4.3) |
| pending_action | object \| null | modeled serializable, always null in H4.1 (FR-006) |
| tool_results | list | v1: always empty (tools are H4.2) |
| errors | list[typed_error] | last errors of the run |

Validation: every value JSON-serializable (JSON-safe test in conformance
suite, FR-005); schema version must match `AGENT_STATE_SCHEMA_VERSION`.

### graph-topology-v1.json

Declares the v1 topology (nodes/edges/entry) that runs record:

| Node | Responsibility | Effect |
| --- | --- | --- |
| start | normalize input, set intent=null, init context | none |
| generate_reply | model gateway structured output (reply-schema-v1), record model call | none |
| persist_reply | persist assistant message + close run | assistant message effect (ledger) |

Edges: `start → generate_reply → persist_reply → end`. No tools, no
interrupts (H4.3). `topology_version = 1`.

### reply-schema-v1.json

Structured assistant output (FR-011):

| Field | Type | Validation |
| --- | --- | --- |
| reply_text | string | 1..2000 chars; uncertainty declared in plain text (R-13) |
| refs | list[product_ref] | empty in v1; `{entity, id}` typed refs arrive with H4.2 tools |

Invalid outputs are rejected or retried a bounded number of times
(`AGENT_MODEL_MAX_RETRIES`, default 2); 0 invalid content reaches state
(FR-011).

## Retention

- `chat_sessions` + `chat_messages`: kept while the account exists; deleted
  with the user (UM-H6-011 — out of scope here, policy recorded in
  FR-008).
- Checkpoints (LangGraph threads): purged after
  `AGENT_CHECKPOINT_RETENTION_DAYS` (default 30) of session inactivity by
  the scheduler maintenance duty `purge_agent_checkpoints` (R-09); history
  is never touched.
