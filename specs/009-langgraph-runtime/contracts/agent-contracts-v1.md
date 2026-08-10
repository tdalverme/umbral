# Contracts: Runtime LangGraph (H4.1)

**Feature**: 009-langgraph-runtime | **Date**: 2026-08-09

Planning contract for the H4.1 runtime. Three new machine-checkable files
under `contracts/agent/v1/`, one additive update to the events registry,
and the conformance rules that validate them. No OpenAPI changes (FR-020).

## 1. State schema — `contracts/agent/v1/state-schema-v1.json`

Declares the v1 checkpointed state shape (FR-004, FR-005).

```json
{
  "registry_version": "agent-state-schema-v1",
  "contract_version": "1",
  "schema_version": 1,
  "serializable": true,
  "fields": [
    {"name": "schema_version", "kind": "integer", "required": true},
    {"name": "messages", "kind": "list", "item": "chat_message", "required": true},
    {"name": "context", "kind": "object", "serializable": true, "required": true},
    {"name": "intent", "kind": "nullable_object", "required": true},
    {"name": "pending_action", "kind": "nullable_object", "required": true},
    {"name": "tool_results", "kind": "list", "required": true},
    {"name": "errors", "kind": "list", "item": "typed_error", "required": true}
  ]
}
```

Conformance rules:
- `schema_version` must equal `AGENT_STATE_SCHEMA_VERSION` (default 1) in
  every checkpoint; runs record it (FR-004, FR-016).
- A conformance test instantiates the agent state module and proves every
  value is JSON-serializable (JSON-safe, FR-005) and that a round-trip
  through the checkpointer preserves the fields.
- `pending_action` is modeled but always `null` in H4.1 (FR-006); the test
  asserts the field exists and is serializable.
- A state with a foreign `schema_version` must either migrate or be
  declared incompatible by a typed error — never silently lose context
  (FR-009). The conformance suite covers the version-mismatch path.

## 2. Graph topology — `contracts/agent/v1/graph-topology-v1.json`

Declares the v1 topology every run records.

```json
{
  "registry_version": "agent-graph-topology-v1",
  "contract_version": "1",
  "topology_version": 1,
  "entry": "start",
  "nodes": [
    {"name": "start", "kind": "node"},
    {"name": "generate_reply", "kind": "node"},
    {"name": "persist_reply", "kind": "node"}
  ],
  "edges": [
    {"from": "start", "to": "generate_reply"},
    {"from": "generate_reply", "to": "persist_reply"},
    {"from": "persist_reply", "to": "end"}
  ],
  "tools": [],
  "interrupts": []
}
```

Conformance rules:
- `topology_version` must equal `AGENT_GRAPH_TOPOLOGY_VERSION` (default 1);
  runs record it (FR-016).
- The graph builder must produce exactly this topology; the conformance
  test compares nodes/edges/entry and asserts `tools == []` and
  `interrupts == []` for v1 (tools: H4.2, interrupts: H4.3).

## 3. Reply schema — `contracts/agent/v1/reply-schema-v1.json`

Structured output contract for the model gateway (FR-010..FR-012).

```json
{
  "registry_version": "agent-reply-schema-v1",
  "contract_version": "1",
  "schema_version": "reply-v1",
  "fields": {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "refs": {"kind": "list", "item": {"entity": "string", "id": "string"}}
  }
}
```

Conformance rules:
- The gateway validates every response against this schema; invalid
  outputs are rejected or retried at most `AGENT_MODEL_MAX_RETRIES` (2)
  times; 0 invalid content reaches state (FR-011).
- Every call records `schema_version = reply-v1` plus model and prompt
  versions and usage (FR-012).
- `refs` is empty-capable in v1; typed refs arrive with H4.2 tools
  (R-13).

## 4. Events registry — additive update

`contracts/events/v1/events-registry.json` gains two additive types
(contract version bumped to 2, R-07):

| Event type | Payload keys | When emitted |
| --- | --- | --- |
| `chat.session_created.v1` | `session_id`, `search_profile_id` | session created |
| `chat.message_created.v1` | `session_id`, `message_id`, `role` | message persisted |

Conformance: the existing `validate_event` machinery (application/events)
accepts the new types and still rejects unknown types; the events registry
conformance test covers the two new types and PII `forbidden_keys` (0
message text in payloads, FR-018).

## No other contract changes

- OpenAPI: unchanged (0 HTTP chat contracts, FR-020).
- Search-profile, scoring, criteria, feedback, learning contracts:
  unchanged (runtime consumes them, does not modify them).
