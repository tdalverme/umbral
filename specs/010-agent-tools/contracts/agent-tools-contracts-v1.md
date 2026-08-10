# Contracts: Tools explicitas y permisos (H4.2)

**Feature**: 010-agent-tools | **Date**: 2026-08-09

Planning contract for the H4.2 tools. New machine-checkable files: agent
schemas v2 (state/topology/reply), the tool contract v1, and an additive
update to the events registry. No OpenAPI changes (FR-025).

## 1. Tool contract — `contracts/agent/tools/tool-contract-v1.json`

Declares the common contract every tool must satisfy (FR-001..FR-004).

```json
{
  "registry_version": "agent-tool-contract-v1",
  "contract_version": "1",
  "tools": [
    {
      "name": "get_search_profile",
      "description": "Lee el perfil autorizado de la sesion: snapshot vigente, criterios ejecutables y estado del radar.",
      "mutating": false,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "input_schema": {},
      "output_schema": {"profile_id": "uuid", "state": "string", "snapshot": "object", "criteria": "array"},
      "output_limits": {"max_items": 1, "forbidden_keys": ["geometry", "value", "free_feedback"]}
    },
    {
      "name": "propose_search_profile_update",
      "description": "Produce un diff validado con impacto y crea una propuesta durable pendiente; no modifica el perfil.",
      "mutating": true,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "idempotent": true,
      "input_schema": {"change": "object"},
      "output_schema": {"proposal_id": "uuid", "diff": "object", "impact": "object", "state": "pending", "expires_at": "datetime"}
    },
    {
      "name": "apply_search_profile_update",
      "description": "Aplica una propuesta pendiente con confirmacion explicita e idempotency key; versiona el perfil y dispara recomputacion.",
      "mutating": true,
      "requires_confirmation": true,
      "timeout_seconds": 10,
      "idempotent": true,
      "input_schema": {"proposal_id": "uuid", "confirmation": "boolean", "idempotency_key": "string"},
      "output_schema": {"proposal_id": "uuid", "state": "approved", "profile_version": "int", "run_id": "uuid"}
    },
    {
      "name": "find_matches",
      "description": "Devuelve los recommendation items persistentes del ultimo run publicado; solo lectura, nunca calcula.",
      "mutating": false,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "input_schema": {"page": "int", "limit": "int"},
      "output_schema": {"run_id": "uuid|null", "items": "array", "total": "int", "stale": "boolean"}
    },
    {
      "name": "explain_match",
      "description": "Recupera la explicacion persistida de un item y declara datos faltantes e incertidumbre.",
      "mutating": false,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "input_schema": {"item_id": "uuid"},
      "output_schema": {"item_id": "uuid", "score_version": "string", "reasons": "array", "risks": "array", "missing_data": "array", "evidence_refs": "array"}
    },
    {
      "name": "compare_listings",
      "description": "Compara listings del radar de la sesion con la comparacion estructurada persistida; sin ganador generativo.",
      "mutating": false,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "input_schema": {"listing_ids": "array"},
      "output_schema": {"comparison": "object", "dimensions": "array", "missing": "array"}
    },
    {
      "name": "record_feedback",
      "description": "Registra like/dislike con razones opcionales, idempotente; devuelve la propuesta de aprendizaje cuando aplica.",
      "mutating": true,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "idempotent": true,
      "input_schema": {"item_id": "uuid", "decision": "like|dislike", "reason_keys": "array", "idempotency_key": "string"},
      "output_schema": {"event_id": "uuid", "noop": "boolean", "learning_proposal_id": "uuid|null"}
    },
    {
      "name": "search_urban_context",
      "description": "Consulta signals urbanas versionadas de un listing respetando la precision geografica autorizada.",
      "mutating": false,
      "requires_confirmation": false,
      "timeout_seconds": 10,
      "input_schema": {"listing_id": "uuid", "signal_types": "array"},
      "output_schema": {"signals": "array", "precision": "string"}
    }
  ]
}
```

Conformance rules:
- The registry module (`agent/tools/registry.py`) loads this contract and
  exposes exactly these 8 tools with their schemas; a conformance test
  asserts name/mutating/confirmation/idempotency flags and that `output_limits`
  reuse the events registry `forbidden_keys` subset (FR-001, FR-003).
- Every executor call validates `input_schema` first; out-of-schema args are
  rejected with a typed error and 0 effects (FR-002).
- `requires_confirmation: true` tools refuse to run without the confirmation
  flag; `mutating: true` tools require the idempotency key per policy
  (FR-010, FR-012).
- Outputs are redacted per `output_limits` (max_items, forbidden_keys,
  FR-003).

## 2. State schema — `contracts/agent/v2/state-schema-v2.json`

```json
{
  "registry_version": "agent-state-schema-v2",
  "contract_version": "2",
  "schema_version": 2,
  "serializable": true,
  "fields": [
    {"name": "schema_version", "kind": "integer", "required": true},
    {"name": "messages", "kind": "list", "item": "chat_message", "required": true},
    {"name": "context", "kind": "object", "serializable": true, "required": true},
    {"name": "intent", "kind": "nullable_object", "required": true},
    {"name": "pending_action", "kind": "nullable_object", "required": true},
    {"name": "tool_calls", "kind": "list", "item": "tool_call", "required": true},
    {"name": "tool_results", "kind": "list", "item": "tool_result", "required": true},
    {"name": "errors", "kind": "list", "item": "typed_error", "required": true}
  ]
}
```

Conformance rules:
- `schema_version` must equal `AGENT_TOOLS_STATE_SCHEMA_VERSION` (2) in
  every checkpoint; runs record it (FR-004, FR-016).
- `tool_call`: `{tool: string, args: object}`; `tool_result`:
  `{tool, status: ok|error, result: object|null, error_code: string|null}`
  (redacted output only).
- `pending_action` may hold `{kind: "proposal", proposal_id}`; the durable
  proposal object is the source of truth (R-03), never duplicated in state.
- Checkpoints with `schema_version = 1` are declared incompatible with a
  typed `AgentStateIncompatible` error (R-02, FR-009 of H4.1); 0 silent
  context loss.

## 3. Graph topology — `contracts/agent/v2/graph-topology-v2.json`

```json
{
  "registry_version": "agent-graph-topology-v2",
  "contract_version": "2",
  "topology_version": 2,
  "entry": "start",
  "nodes": [
    {"name": "start", "kind": "node"},
    {"name": "generate_reply", "kind": "node"},
    {"name": "run_tools", "kind": "node"},
    {"name": "persist_reply", "kind": "node"}
  ],
  "edges": [
    {"from": "start", "to": "generate_reply"},
    {"from": "generate_reply", "to": "run_tools", "condition": "tool_calls"},
    {"from": "run_tools", "to": "generate_reply", "condition": "loop"},
    {"from": "generate_reply", "to": "persist_reply", "condition": "no_tool_calls"}
  ],
  "tools": [
    "get_search_profile", "propose_search_profile_update",
    "apply_search_profile_update", "find_matches", "explain_match",
    "compare_listings", "record_feedback", "search_urban_context"
  ],
  "interrupts": []
}
```

Conformance rules:
- `topology_version` must equal `AGENT_TOOLS_TOPOLOGY_VERSION` (2); runs
  record it (FR-016).
- The graph builder must produce exactly this topology; the conformance test
  compares nodes/edges/entry, asserts `tools` matches the tool contract and
  `interrupts == []` (interrupts are H4.3).
- The tool loop is bounded by `AGENT_TOOLS_MAX_CALLS_PER_TURN` (5): the
  conformance test asserts the loop terminates and each tool call produces
  exactly one `agent_node_runs` row with `node_kind='tool'` (R-14, FR-004).

## 4. Reply schema — `contracts/agent/v2/reply-schema-v2.json`

```json
{
  "registry_version": "agent-reply-schema-v2",
  "contract_version": "2",
  "schema_version": "reply-v2",
  "fields": {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "refs": {"kind": "list", "item": {"entity": "string", "id": "string"}},
    "tool_calls": {"kind": "list", "item": {"tool": "string", "args": "object"}, "max_items": 5}
  }
}
```

Conformance rules:
- The gateway validates every response against this schema; invalid outputs
  are rejected or retried at most `AGENT_MODEL_MAX_RETRIES` (2) times; 0
  invalid content reaches state (FR-011).
- `tool_calls` entries must name tools present in the tool contract and args
  must satisfy their `input_schema`; invalid entries invalidate the output
  (R-14).
- `refs` are populated from tool results (`{entity, id}` typed refs); 0 refs
  to objects outside the session scope (FR-002).

## 5. Events registry — additive update

`contracts/events/v1/events-registry.json` gains two additive types
(R-09); the version fields follow the actual state of the file at
implementation time (today `contract_version "1"`, registry `events-v1`,
with the chat types already present):

| Event type | Payload keys | When emitted |
| --- | --- | --- |
| `search_profile.update_proposed.v1` | `proposal_id`, `search_profile_id`, `base_profile_version` | propose persisted a pending proposal |
| `search_profile.update_applied.v1` | `proposal_id`, `search_profile_id`, `profile_version` | apply approved the proposal and versioned the profile |

Conformance: the existing `validate_event` machinery accepts the new types
and still rejects unknown types; payloads contain 0 forbidden keys (0 free
text, 0 geometry — FR-003/FR-018).

Tool invocations emit NO product events: their audit trail is
`agent_node_runs` with `node_kind='tool'` (R-09, same decision as H4.1 R-07
for graph runs).

## No other contract changes

- OpenAPI: unchanged (0 HTTP chat contracts, FR-025).
- Search-profile, scoring, criteria, feedback, learning, chat contracts:
  unchanged (tools consume existing services, R-06/R-07/R-08).
- `contracts/agent/v1/*`: intact, audited prior version (R-02).
