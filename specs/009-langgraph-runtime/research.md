# Research: Runtime LangGraph (H4.1)

**Feature**: 009-langgraph-runtime | **Date**: 2026-08-09

Decisions taken during planning. Each entry records the decision, the
rationale, and the alternatives considered.

## R-01 — Adopt the LangGraph library as the conversational runtime

**Decision**: Add `langgraph` + `langgraph-checkpoint-postgres` (and their
transitive deps, pinned via `uv.lock`) as the first agent runtime
dependencies, with the graph built in the `agent` layer and the Postgres
checkpointer wired through `infrastructure/agent`.

**Rationale**: The constitution mandates LangGraph for the conversational
orchestrator ("MUST use LangGraph with explicit, permissioned application
tools and persistent checkpoints") and the whole H4 epic (state schema,
topology, checkpoints, streaming, resume, later interrupts in H4.3) maps
1:1 to the library's StateGraph/checkpointer/astream primitives. Adopting
it now avoids building a throwaway in-house state machine in H4.1 that
H4.2/H4.3 would replace. Verified against PyPI: `langgraph-checkpoint-postgres`
3.1.2 requires `langgraph-checkpoint>=4.1.0,<5.0.0`, `orjson>=3.11.5`,
`psycopg-pool>=3.2.0`, `psycopg>=3.2.0` (psycopg already a project
dependency); the saver requires `.setup()` to create its tables and manual
connections must use `autocommit=True` + `row_factory=dict_row`. The README
mandates `LANGGRAPH_STRICT_MSGPACK=true` (or an explicit
`allowed_msgpack_modules` list) to prevent code execution from compromised
checkpoint blobs — required for our security posture.

**Alternatives considered**:
- In-house state machine (typed state + custom tables + custom resume
  logic): would satisfy H4.1 requirements alone, but violates the
  constitution, duplicates the interrupt/streaming machinery H4.3 needs and
  would be deleted shortly after — rejected as speculative throwaway.
- `langgraph-checkpoint` (base package only) without `langgraph`: gives the
  saver but not the graph/streaming primitives; rejected because the
  runtime (astream, resume, later interrupts) lives in `langgraph`.

## R-02 — Sessions and messages are product tables; checkpoints are operational state

**Decision**: `chat_sessions` and `chat_messages` are first-class persistent
tables owned by the app (migration `0009_langgraph_runtime`); LangGraph
checkpoints live in library-managed tables (created by `saver.setup()`) and
are never queried as product truth.

**Rationale**: Principle I of the constitution ("checkpoints MUST NOT
replace searches, listings, recommendations, feedback, or audit events as
product truth") plus spec FR-001/FR-002. The chat history the user reads is
`chat_messages`; the checkpoint only holds the in-flight execution state
that makes resume possible.

**Alternatives considered**:
- Checkpoint-only conversation state: rejected (violates constitution;
  retention/retrieval would depend on library internals).
- Messages stored inside checkpoint blobs with a denormalized copy:
  rejected — two sources of truth and fragile against schema migrations.

## R-03 — Checkpointer tables are library-managed and excluded from Alembic

**Decision**: Migration `0009_langgraph_runtime` creates only our tables;
LangGraph's `checkpoints`/`checkpoint_writes`/`checkpoint_blobs` (and any
internal tables) are created by `saver.setup()` at first use and excluded
from Alembic autogenerate via an `include_object` filter so the drift check
does not flag them.

**Rationale**: The library owns its schema and versioning (its checkpointer
has its own internal migrations); mixing it into our Alembic chain would
create drift noise and false incompatibilities. The exclusion is documented
in the migration and in `alembic/env.py`.

**Alternatives considered**:
- Fork/manage the checkpoint tables ourselves in Alembic: rejected —
  fragile against library upgrades and duplicate of the library's own
  migration logic.
- Let drift check report them and whitelist via config: same outcome, more
  brittle; explicit `include_object` filter is clearer.

## R-04 — Zero duplicate effects via an applied-effects ledger in state

**Decision**: Every effect a run can apply (persist user message, persist
assistant message) records a marker in `context.effects_applied`
(`{effect_key: run_id}`) inside the checkpointed state; on resume the graph
nodes skip effects already marked. Effects are applied through a single
`apply_effect` helper in the agent layer.

**Rationale**: Spec FR-014 (resume without repeating effects, 0
duplicates). In H4.1 the effect surface is small (two message effects), so
a ledger is the minimal deterministic mechanism; H4.2 tools will reuse the
same ledger via their idempotency keys. The ledger lives in `context`
(serializable dict), keeping the state schema v1 fields stable per FR-004.

**Alternatives considered**:
- Recompute "did this run apply the effect" from DB state alone (e.g., does
  the assistant message for this run already exist?): works for messages
  but does not generalize to H4.2 tool effects; the ledger is the
  generalized answer.
- External dedupe store: rejected as extra machinery for H4.1.

## R-05 — Model provider deferred; gateway seam with fake and managed HTTP adapter

**Decision**: The model gateway is a port in `application/agent` with two
adapters: `FakeModelGateway` (default, deterministic, for tests/local) and
`ManagedModelGateway` (HTTP JSON structured-output endpoint with timeout,
bounded retry with backoff, token usage, model/prompt/schema versions),
mirroring the existing criteria extraction seam (`EXTRACTION_PROVIDER` /
`ManagedStructuredExtractor`). Provider selection remains deferred: the
real provider ADR is an H4.4 concern, consistent with the criteria-observations
precedent (provider choice deferred to plan/ADR).

**Rationale**: Spec FR-010..FR-012 require a single provider-agnostic
adapter with structured outputs, timeout, bounded retry, usage and versions
without leaking the provider into domain. The criteria extractor proves the
pattern works in this codebase with 0 new provider SDKs.

**Alternatives considered**:
- Install an SDK (openai/anthropic) now and commit to a provider:
  rejected — provider choice is deliberately deferred (see criteria
  precedent), and the managed HTTP adapter keeps the option open.
- LangChain model abstraction (`langchain` package): rejected — heavier
  surface than needed; the gateway port is our own small contract.

## R-06 — Concurrency guard via partial unique index; interrupted runs require resume

**Decision**: `agent_graph_runs` carries a partial unique index on
`(session_id) WHERE status IN ('pending','running')`; claiming a run is an
atomic INSERT (or an UPDATE `resumed_at`/`attempt` on the same run for
resume). A second request to a session with a non-terminal run gets the
typed error `ChatExecutionInProgress` ("ejecucion en curso"); no queueing
and no duplicate ignoring (clarification 2026-08-09). Interrupted runs must
be resumed; there is no cancel/abandon path in H4.1 (H4.3 adds it with
human-in-the-loop).

**Rationale**: Clarification (reject with typed recoverable state) +
FR-015 (0 parallel executions). The DB constraint gives the guarantee even
under concurrency; the typed error gives the client a recoverable state.

**Alternatives considered**:
- Application-level lock (in-memory/Redis): rejected — in-memory does not
  survive restarts and Redis adds a runtime dependency for a guarantee the
  DB gives for free.
- Queue the second request: rejected by the clarification (0 colas).

## R-07 — Chat product events are additive to the events registry

**Decision**: `contracts/events/v1/events-registry.json` gains two additive
types, `chat.session_created.v1` and `chat.message_created.v1` (contract
version bump to 2), emitted by the chat service through the existing events
path. Run/node/model-call records stay in their tables (operational
audit), not as product events.

**Rationale**: DoD #4 ("emite telemetria y eventos de auditoria cuando
cambia estado de producto") — session/message creation is product state;
spec FR-020 prohibits HTTP surfaces and tools, not events. The registry's
`validate_event` machinery keeps the additions conformance-checked.
Graph runs are operational machinery, their audit trail is the run tables
(FR-016..FR-018).

**Alternatives considered**:
- No events at all (run tables only): rejected — violates DoD #4 and
  leaves session/message creation without product audit events.
- Emit events for run lifecycle too: rejected — the run tables already
  record version/latency/status/usage/correlation; duplicating as events
  doubles the audit path.

## R-08 — Settings follow the flat AGENT_*/CHAT_* convention

**Decision**: New settings are flat env vars with domain prefixes
(`AGENT_MODEL_PROVIDER`, `AGENT_MODEL_NAME`, `AGENT_MODEL_TIMEOUT_SECONDS`,
`AGENT_MODEL_MAX_RETRIES`, `AGENT_STATE_SCHEMA_VERSION`,
`AGENT_GRAPH_TOPOLOGY_VERSION`, `AGENT_CHECKPOINT_RETENTION_DAYS`,
`AGENT_STRICT_MSGPACK`, `CHAT_MESSAGE_MAX_LENGTH`) registered in
`Settings._known_fields`, validated at startup with safe defaults, mirroring
`CRITERIA_*`/`MATCHING_*`.

**Rationale**: Project convention (flat vars, `_known_fields`, startup
validation); no new config machinery. `AGENT_STRICT_MSGPACK` defaults to
`true` (R-01 security note).

**Alternatives considered**: nested settings object per domain: rejected —
breaks the existing flat convention.

## R-09 — Checkpoint retention purge via scheduler maintenance

**Decision**: `infrastructure/agent/purge.py` implements
`purge_agent_checkpoints(retention_days)` which deletes checkpoint threads
of sessions inactive longer than the window (using the saver's thread
deletion API in the pinned version; if unavailable, the deletion uses the
saver's documented cleanup and is verified by the integration test). It is
registered as a scheduler maintenance duty in `workers/scheduler.py`
(recovery-first order, like `purge_request_fingerprints`), and NEVER touches
`chat_sessions`/`chat_messages` (account-lifetime retention, clarification
2026-08-09).

**Rationale**: Clarification (checkpoints = short operational window,
default 30 days, parametrizable; history untouched) + FR-008. The scheduler
already hosts periodic maintenance duties; a new RQ job type would be
heavier than needed.

**Alternatives considered**:
- RQ job for purge: rejected — periodic maintenance fits the existing
  scheduler duties pattern without queue traffic.
- Purge on read (lazy): rejected — no deterministic guarantee that
  expired checkpoints disappear; the scheduler gives a bounded window.

## R-10 — Node runs single table; tool runs arrive with H4.2

**Decision**: `agent_node_runs` records every node execution with
`node_kind IN ('node','tool')`; in H4.1 only `node` rows exist. Tool rows
are added in H4.2 without a new table.

**Rationale**: FR-017 requires node/tool runs linked to the graph run; the
H4.1 topology has no tools, but the table shape must not force a migration
in H4.2. One table with a discriminator is the minimum that covers both.

**Alternatives considered**: separate `agent_tool_runs` table now: rejected
— empty table for a concept H4.1 does not have (nothing speculative).

## R-11 — Messages persist only complete replies; partial output lives in the checkpoint

**Decision**: The assistant message is persisted by the terminal node only
after the reply is complete (with an effect marker, R-04); streamed
fragments exist only in the checkpoint state and the typed runtime events.
A run interrupted mid-generation leaves no partial message (clarification
2026-08-09, FR-014).

**Rationale**: Keeps message immutability simple (message = complete
content) and history free of partial artifacts.

**Alternatives considered**: persist partial messages with a
partial→complete transition: rejected by the clarification (0 mensajes
parciales).

## R-12 — Session state mirrors the search profile state

**Decision**: `chat_sessions.status` derives from the linked search
profile: radar paused/archived → session paused/archived, which rejects new
turns while keeping history readable. No own session transitions exist
(clarification 2026-08-09, FR-001).

**Rationale**: The search profile is the radar's source of truth (H2.3);
the session is an accessory of the radar and must not invent its own
lifecycle.

**Alternatives considered**: independent session transitions with own
events: rejected — extra machinery with no product driver in H4.1.

## R-13 — Reply schema v1 is minimal (text + typed references)

**Decision**: `contracts/agent/v1/reply-schema-v1.json` defines the
structured assistant output for H4.1: `reply_text` (bounded length) plus an
empty-capable `refs` list of typed product references; uncertainty is a
plain-text declaration for now. Grounding against real evidence arrives
with the H4.2 tools (`find_matches`, `explain_match`).

**Rationale**: In H4.1 the graph has no tools and no retrieval, so a richer
schema would be speculative; the minimal schema exercises the structured-
output path (validation, versions, invalid-output rejection) that H4.2
extends with tool-driven fields.

**Alternatives considered**: full explanation/reference schema now:
rejected — H4.2 defines the tools that produce those fields.

## R-14 — History and session retrieval stay service-level in H4.1

**Decision**: The chat service exposes ordered history retrieval and
session lookup with ownership checks; pagination and HTTP contracts are
H4.3 concerns (FR-020).

**Rationale**: FR-020 forbids HTTP chat contracts in this increment; the
service surface is what the harness, tests and (later) the H4.3 API use.

**Alternatives considered**: an internal HTTP endpoint now: rejected
(FR-020).
