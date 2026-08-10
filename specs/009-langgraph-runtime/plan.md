# Implementation Plan: Runtime LangGraph

**Branch**: `main` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification for UM-H4-001 through UM-H4-006 (Epica
H4.1 - Runtime LangGraph), including the clarification sessions 2026-08-09
(retention: sessions/messages live with the account, checkpoints purge
after a short inactivity window, default 30 days, parametrizable; a second
request to a session with an active run is rejected with a typed
"ejecucion en curso" state — no queueing, client retries; a session's state
mirrors its search profile state; only complete assistant replies are
persisted, fragments live in the checkpoint).

## Summary

First increment of the conversational radar (H4): the persistent, resumable,
isolated and auditable runtime the H4.2 tools, H4.3 behavior/UI and H4.4
evals build on. Concretely:

- `chat_sessions` + `chat_messages` as first-class product tables (FR-001..
  FR-003) with a `application/chat` service (ownership, state mirroring,
  ordered history, immutability, message limits) and two new product events
  `chat.session_created.v1` / `chat.message_created.v1` in the events
  registry (DoD #4).
- The LangGraph runtime in the `agent` layer: versioned state schema v1,
  topology v1 (`start → generate_reply → persist_reply`), typed runtime
  events, run/node/model-call audit tables (`agent_graph_runs`,
  `agent_node_runs`, `agent_model_calls`), Postgres checkpointer via
  `langgraph-checkpoint-postgres` (R-01/R-03), resume with 0 repeated
  effects via an `effects_applied` ledger in state (R-04), and a
  DB-enforced 0-parallel guarantee per session (R-06).
- The model gateway port (`application/agent`) with `FakeModelGateway`
  (default) and `ManagedModelGateway` (HTTP structured output, timeout,
  bounded retry, usage, model/prompt/schema versions) mirroring the
  criteria extraction seam; provider choice deferred to H4.4 (R-05).
- Checkpoint retention purge as a scheduler maintenance duty
  (`AGENT_CHECKPOINT_RETENTION_DAYS`, default 30) that never touches
  history (R-09).
- `scripts/check-agent.ps1` registered in `check.ps1`; architecture tests
  for the `agent` layer; migration `0009_langgraph_runtime`.

The increment adds no HTTP chat contracts, no web surface and no product
tools (FR-020); tool runs and interrupts arrive in H4.2/H4.3.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14`; no web/TypeScript surface

**Primary Dependencies**: existing (SQLAlchemy 2, Psycopg 3, Alembic,
Pydantic v2) plus new runtime dependencies `langgraph` and
`langgraph-checkpoint-postgres` (>=3.1.2, pulls `langgraph-checkpoint`,
`orjson`, `psycopg-pool`; psycopg already present) — pinned exactly via
`uv.lock` (R-01). The `agent` layer is already defined in the import-linter
contracts (pyproject.toml); no new layer needed.

**Storage**: Postgres. Migration `0009_langgraph_runtime` creates
`chat_sessions`, `chat_messages`, `agent_graph_runs`, `agent_node_runs`,
`agent_model_calls`; the LangGraph checkpoint tables are library-managed
(created by `saver.setup()`), excluded from Alembic autogenerate via
`include_object` (R-03). No new storage/queue infra.

**Testing**: pytest (contract conformance for the three agent contracts +
events registry; unit for chat service, run recorder, gateway adapters,
purge; integration with testcontainers Postgres for the checkpointer,
resume/no-dup, isolation and concurrency; migrations test for 0009),
Ruff, mypy, import-linter architecture tests, Alembic drift checks,
`scripts/check-agent.ps1` registered in `check.ps1` (FR-019).

**Target Platform**: modular monolith; the runtime is driven by tests, the
harness and (from H4.3) the API — no HTTP surface in this increment.

**Performance Goals**: a full turn with `FakeModelGateway` completes in
milliseconds (integration test asserts the run reaches `completed` and the
first typed event arrives before the run finishes); CI surfaces complete in
seconds. Latency budgets against a real provider are H4.4/H6.3 concerns.

**Constraints**: resume without repeating effects (FR-014, R-04); typed
rejection of concurrent turns (FR-015, R-06); checkpoints aislados por
usuario/sesion (FR-007); checkpoint retention without touching history
(FR-008, R-09); schema version migration or declared incompatibility
(FR-009); provider-agnostic gateway with structured outputs and bounded
retry (FR-010..FR-012); 0 HTTP chat contracts and 0 tools (FR-020); 0 PII
in runs/logs/events (FR-018); `LANGGRAPH_STRICT_MSGPACK=true` (R-01).

**Scale/Scope**: beta cohort; one active run per session; message text
bounded (`CHAT_MESSAGE_MAX_LENGTH`, default 4000); checkpoint purge runs as
a scheduler maintenance duty; five tables, three contract JSON files, one
registry update, one migration, one harness script.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1.*

| Principle | Before research | After design | Evidence |
| --- | --- | --- | --- |
| Persistent radar truth | PASS | PASS | Sessions/messages are product tables (FR-001/FR-002); checkpoints are operational state, never product truth (R-02); the ledger keeps chat from being the only place decisions live (Principle I). |
| Auditable deterministic matching | PASS | PASS | Run/node/model-call tables record version, state, latency, errors, usage and correlation (FR-016..FR-018); 0 generative decisions: the gateway only produces schema-validated replies (FR-011) and the graph has no ranking/tool surface (Principle II). |
| Layer boundaries | PASS | PASS | `agent` (LangGraph) sits in the existing `agent|api|workers` layer; it consumes `application/chat`, `application/agent` ports and infrastructure adapters via composition; `application/chat|agent` and `domain` never import langgraph; architecture tests enforce it (Principle III, R-03). |
| Data lineage and observability | PASS | PASS | Messages trace to their graph run; runs trace to schema/topology versions and correlation; model calls record model/prompt/schema versions and usage; 0 PII in runs, logs or event payloads (FR-018, R-07); retention is documented and versioned (FR-008) (Principle V). |
| Versioned prompts, models and schemas | PASS | PASS | `state-schema-v1`, `graph-topology-v1` and `reply-schema-v1` are versioned contracts; every checkpoint records its schema version (FR-004); every model call records model/prompt/schema versions (FR-012); runs are never mutated (Principle II/V). |
| Minimal verifiable scope | PASS | PASS | Scope is exactly UM-H4-001..UM-H4-006: no HTTP chat contracts, no web, no tools, no provider commitment; tool tables/runs arrive with H4.2, interrupts with H4.3, evals/costs with H4.4. |

There are no constitution violations requiring a complexity exception.

## Assumptions and Tradeoffs

- LangGraph is adopted now as the orchestrator library (R-01,
  constitution-mandated): `langgraph` + `langgraph-checkpoint-postgres`
  pinned via `uv.lock`; the rejected alternative (in-house state machine)
  is recorded in research.md. The library adds runtime dependencies the
  project did not have; this is the constitution's explicit direction.
- Checkpoint tables are library-managed and excluded from our Alembic
  metadata (R-03); migration `0009` creates only the five app tables. The
  drift check stays green via the `include_object` filter, documented in
  `alembic/env.py`.
- Zero-duplicate effects use an `effects_applied` ledger inside
  `context` in the checkpointed state (R-04); the H4.2 tools reuse it via
  their idempotency keys.
- Model provider remains deferred: `AGENT_MODEL_PROVIDER` defaults to
  `fake`; the managed adapter is HTTP-based like the criteria extractor;
  the provider ADR is an H4.4 concern (R-05).
- Concurrency: a second request to a session with a non-terminal run is
  rejected with `ChatExecutionInProgress` (FR-015, R-06); interrupted runs
  must be resumed — there is no cancel path in H4.1 (H4.3 adds it); the
  unique partial index is the enforcement point.
- Session status mirrors the search profile status (R-12); no own session
  transitions.
- Only complete assistant replies are persisted (R-11); partial fragments
  exist in checkpoint state and typed events only.
- Product events: exactly `chat.session_created.v1` and
  `chat.message_created.v1` added to the events registry (R-07); run
  lifecycle stays in the audit tables.
- The thread-deletion API available in the pinned
  `langgraph-checkpoint-postgres` version is the purge mechanism (R-09);
  if the pinned version lacks a supported deletion API, the purge falls
  back to the saver's documented cleanup and the integration test pins the
  behavior. This is an implementation-time verification, not a scope
  change.
- History pagination and HTTP contracts are H4.3 (R-14, FR-020); H4.1
  exposes service-level retrieval with ownership checks.

Detailed decision records and rejected alternatives are in
[research.md](./research.md).

## Architecture

```mermaid
flowchart LR
    API["api/ (H4.3) — out of scope"]
    RUNTIME["agent/runtime.py — run/stream/resume, typed events"]
    GRAPH["agent/graph.py — StateGraph topology v1"]
    STATE["agent/state.py — state schema v1 (serializable)"]
    GW_PORT["application/agent/ports.py — ModelGateway"]
    FAKE["infrastructure/agent/model_gateway/fake.py"]
    MANAGED["infrastructure/agent/model_gateway/managed.py (HTTP, retry, usage)"]
    CP["infrastructure/agent/checkpointer.py — PostgresSaver (strict msgpack)"]
    PURGE["infrastructure/agent/purge.py — retention duty"]
    CHAT["application/chat/service.py — sessions, messages, ownership, state mirror"]
    RUNS["application/agent/service.py — run/node/model-call recorder"]
    EVENTS["application/events — chat.session_created.v1, chat.message_created.v1"]
    MODELS["db/models/chat.py + agent.py — 5 tables"]
    REPOS["db/repositories/chat.py + agent.py"]
    MIG["alembic/versions/0009_langgraph_runtime.py"]
    CONTRACTS["contracts/agent/v1/* + events registry update"]
    TESTS["tests contract/unit/integration/migrations/architecture"]
    HARNESS["scripts/check-agent.ps1 → check.ps1"]

    RUNTIME --> GRAPH
    GRAPH --> STATE
    GRAPH --> GW_PORT
    GW_PORT --> FAKE
    GW_PORT --> MANAGED
    GRAPH --> CP
    RUNTIME --> CHAT
    RUNTIME --> RUNS
    CHAT --> EVENTS
    CHAT --> REPOS
    RUNS --> REPOS
    REPOS --> MODELS
    MODELS --> MIG
    PURGE --> CP
    STATE --> CONTRACTS
    TESTS --> RUNTIME
    HARNESS --> TESTS
    API -. H4.3 .-> RUNTIME
```

All arrows are dependency/use direction. `agent/` is the orchestrator
layer; `application/chat` and `application/agent` are its services;
`infrastructure/agent` holds the adapters. Nothing in `application` or
`domain` imports langgraph (architecture test).

## Module, Interface and Seam Design

| Module | Public Interface | Adapters / consumers | Boundary rule |
| --- | --- | --- | --- |
| `application/chat` | `create_session(user_id, search_profile_id)`, `get_session(user_id, session_id)`, `list_history(user_id, session_id)`, `append_user_message(...)`, `persist_assistant_message(...)`, `assert_accepts_turn(session)` | `agent/runtime.py`, H4.3 API, tests | Ownership + state mirror + immutability + limits; emits chat events; no langgraph |
| `application/agent/ports.py` | `ModelGateway.generate_structured(messages, schema, schema_version, prompt_version, model_version) -> ModelResult` | `infrastructure/agent/model_gateway/*` | Provider-agnostic; returns validated content + usage + versions |
| `application/agent` | `record_graph_run(...)`, `record_node_run(...)`, `record_model_call(...)` | `agent/runtime.py`, `agent/graph.py` | Idempotent by run/node/call id; 0 PII in summaries |
| `agent/state.py` | `StateV1` values + `serialize`/`deserialize` + schema version | `agent/graph.py`, conformance tests | JSON-safe round-trip (FR-005) |
| `agent/graph.py` | `build_topology_v1(gateway, saver, sinks) -> compiled graph` | `agent/runtime.py` | Matches `graph-topology-v1.json`; effects via ledger (R-04) |
| `agent/runtime.py` | `run_turn(session, user_message, resume=False, consumer)` — typed events, claim/release run, resume, reject `ChatExecutionInProgress` | tests, H4.3 API | 0 parallel runs (FR-015); resume with 0 duplicated effects (FR-014) |
| `agent/events.py` | `RunStarted`, `ReplyFragment`, `RunCompleted`, `RunFailed`, `RunInterrupted` (typed, correlation) | runtime, tests | In-process; HTTP contract is H4.3 (FR-013) |
| `infrastructure/agent/checkpointer.py` | `create_postgres_saver(engine) -> PostgresSaver` (setup, autocommit/dict_row, strict msgpack), `delete_thread(session_id)` | graph, purge | Library tables excluded from Alembic (R-03) |
| `infrastructure/agent/purge.py` | `purge_agent_checkpoints(retention_days) -> count` | `workers/scheduler.py` maintenance | Never touches chat tables (R-09) |
| `infrastructure/agent/model_gateway/managed.py` | HTTP structured output: timeout, retry `<=AGENT_MODEL_MAX_RETRIES`, usage, versions | gateway port | Mirrors criteria managed extractor (R-05) |
| `scripts/check-agent.ps1` | pytest surfaces + contract conformance | `check.ps1` (`agentSurface` guard) | Fails hard on any failure (FR-019) |

Do not introduce HTTP endpoints, web components, worker jobs or product
tools in this increment (FR-020). The runtime is composed in tests with
fakes/in-memory saver and in integration with the Postgres saver;
composition wiring for production starts in H4.3.

## Readiness and Failure Isolation

New critical dependencies: Postgres (existing) and the langgraph stack
(pinned). Failure behavior:

- A second request to a session with a `pending`/`running` run: rejected
  with `ChatExecutionInProgress` by the DB partial unique index — the
  client state is typed and recoverable (FR-015, R-06).
- Disconnect mid-run: the run is marked `interrupted`; resume restarts from
  the last checkpoint with `attempt+1`; effects marked in
  `context.effects_applied` are never re-applied (FR-014, R-04/R-11).
- Model timeout / exhausted bounded retry: typed error, run `failed`,
  recoverable state; 0 infinite loops (FR-011).
- Invalid structured output: bounded retry then typed error; 0 invalid
  content reaches state (FR-011).
- Schema version mismatch on resume: migrate or declare incompatible with a
  typed error; 0 silent context loss (FR-009).
- Corrupt/missing checkpoint (purged by retention): resume fails with a
  typed error; history (chat_messages) remains intact — the user can start
  a new run (FR-008/FR-009).
- Cross-user access (manipulated ids): denied in the service before any
  checkpoint access (FR-007).
- A checkpoint purge hitting an active session: the purge only considers
  sessions inactive beyond the window; the active partial unique index
  prevents interference (R-09).

## Configuration and Secret Boundary

No new secrets. New settings (flat env vars behind `Settings`, validated at
startup, safe defaults; registered in `_known_fields`):

- `AGENT_MODEL_PROVIDER` (`fake`) — gateway adapter to compose;
- `AGENT_MODEL_NAME` (`local-fake`) — model version reported in calls;
- `AGENT_MODEL_TIMEOUT_SECONDS` (30) — per-call timeout;
- `AGENT_MODEL_MAX_RETRIES` (2) — bounded retry budget;
- `AGENT_STATE_SCHEMA_VERSION` (1) — state schema version;
- `AGENT_GRAPH_TOPOLOGY_VERSION` (1) — topology version;
- `AGENT_CHECKPOINT_RETENTION_DAYS` (30) — checkpoint purge window;
- `AGENT_STRICT_MSGPACK` (`true`) — safe checkpoint deserialization
  (R-01; also honors `LANGGRAPH_STRICT_MSGPACK`);
- `CHAT_MESSAGE_MAX_LENGTH` (4000) — message text limit (FR-003).

Runs, node runs, model calls, event payloads and purge reports never
contain message text or free content — only ids, versions, counts, codes
and correlation (FR-018).

## Data and Migration Design

Migration `0009_langgraph_runtime` creates five tables (shapes and
validation rules in [data-model.md](./data-model.md)):

1. `chat_sessions` — user + search profile + derived status;
2. `chat_messages` — immutable typed content, lineage to graph run;
3. `agent_graph_runs` — version, status, attempt, latency, errors, usage,
   correlation; partial unique index for the 0-parallel guarantee;
4. `agent_node_runs` — node/tool executions (node_kind discriminator);
5. `agent_model_calls` — model/prompt/schema versions + usage + status.

LangGraph checkpoint tables are library-managed via `saver.setup()` and
excluded from Alembic autogenerate (`include_object` filter, R-03).

## Contracts

Planning contract: [agent contracts v1](./contracts/agent-contracts-v1.md)

Machine-checkable files to add: `contracts/agent/v1/state-schema-v1.json`,
`contracts/agent/v1/graph-topology-v1.json`,
`contracts/agent/v1/reply-schema-v1.json`; additive update to
`contracts/events/v1/events-registry.json` (`chat.session_created.v1`,
`chat.message_created.v1`, contract version 2). No OpenAPI changes
(FR-020).

## Job Idempotency and Recovery

No new RQ job type. New scheduler maintenance duty
`purge_agent_checkpoints` in `workers/scheduler.py` (recovery-first order,
like `purge_request_fingerprints`): deletes checkpoint threads of sessions
inactive beyond `AGENT_CHECKPOINT_RETENTION_DAYS`; idempotent (running
twice is a no-op), never touches chat tables (R-09).

Runtime recovery: interrupted runs resume via the same checkpoint thread;
effects are deduplicated by the ledger (R-04); the run row `attempt`
counter makes resume observable.

## Observability and Audit

Audit coverage:

| Operation | Durable evidence |
| --- | --- |
| session created | `chat_sessions` row + `chat.session_created.v1` event |
| message persisted | `chat_messages` row + `chat.message_created.v1` event |
| graph run executed | `agent_graph_runs` row (version, status, latency, errors, usage, correlation) |
| node execution | `agent_node_runs` row linked to the run |
| model call | `agent_model_calls` row (model/prompt/schema versions, usage, status) |
| checkpoint purge | scheduler log + purge report (ids/counts only) |
| resume with 0 duplicates | run row (`attempt>1`) + no duplicate message rows (test) |

No new telemetry event types beyond the two chat events; no PII in
payloads or summaries (FR-018).

## Delivery and Recovery Topology

No new deployment topology: no API, worker job or web artifacts. The new
library dependencies ride the normal `uv.lock`/CI flow; migration `0009`
runs through the standard Alembic path; the checkpointer's `setup()` runs
lazily at first composition in tests/integration (and from H4.3 in
production wiring) — documented in `runtime-local.md` when deployment docs
are touched. Backup/restore scope: `chat_*` and `agent_*` tables fall under
the existing Postgres backup policy (H1.12); checkpoint tables are
recreatable state (purge-able), excluded from restore-critical data.

## Project Structure

### Documentation (this feature)

```text
specs/009-langgraph-runtime/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── agent-contracts-v1.md
├── checklists/
│   └── requirements.md
└── tasks.md                    # created later by /speckit-tasks
```

### Source Code (repository root)

```text
contracts/
├── agent/v1/
│   ├── state-schema-v1.json        # checkpointed state shape (FR-004/005)
│   ├── graph-topology-v1.json      # v1 topology (FR-016)
│   └── reply-schema-v1.json        # structured output (FR-010..012)
└── events/v1/events-registry.json  # + chat.session_created.v1, chat.message_created.v1
src/umbral/application/chat/
├── contracts.py                # ChatSession, ChatMessage, roles, content, errors
├── ports.py                    # ChatSessionRepository, ChatMessageRepository
└── service.py                  # create/get/history/append/persist/mirror/guard
src/umbral/application/agent/
├── contracts.py                # GraphRun, NodeRun, ModelCall values + states
├── ports.py                    # run/node/call repositories + ModelGateway
└── service.py                  # record_* (idempotent, 0 PII)
src/umbral/agent/
├── state.py                    # state schema v1 values (JSON-safe)
├── events.py                   # typed runtime events
├── graph.py                    # build_topology_v1 (StateGraph)
└── runtime.py                  # run_turn/stream/resume/guard
src/umbral/infrastructure/agent/
├── checkpointer.py             # Postgres saver factory (setup, strict msgpack) + delete
├── purge.py                    # purge_agent_checkpoints (retention)
└── model_gateway/
    ├── fake.py                 # FakeModelGateway (default)
    └── managed.py              # ManagedModelGateway (HTTP, retry, usage)
src/umbral/infrastructure/db/models/chat.py    # ChatSessionRow, ChatMessageRow
src/umbral/infrastructure/db/models/agent.py   # AgentGraphRunRow, AgentNodeRunRow, AgentModelCallRow
src/umbral/infrastructure/db/repositories/chat.py
src/umbral/infrastructure/db/repositories/agent.py
alembic/versions/0009_langgraph_runtime.py
alembic/env.py                     # + include_object filter for langgraph tables
scripts/check-agent.ps1            # new harness surface (mirrors check-*.ps1)
tests/
├── contract/test_agent_state_schema.py
├── contract/test_agent_graph_topology.py
├── contract/test_agent_reply_schema.py
├── contract/test_agent_chat_events.py
├── contract/test_agent_harness.py
├── unit/application/chat/test_service.py
├── unit/application/agent/test_run_recorder.py
├── unit/agent/test_state.py
├── unit/agent/test_graph.py            # in-memory saver + fake gateway
├── unit/infrastructure/agent/test_managed_gateway.py
├── unit/infrastructure/agent/test_purge.py
├── integration/chat/test_session_repo.py
├── integration/agent/test_checkpointer.py
├── integration/agent/test_runtime_e2e.py
├── integration/agent/test_runtime_isolation.py
├── migrations/test_0009_langgraph_runtime.py
└── architecture/test_agent_boundaries.py
```

**Structure Decision**: keep the accepted modular monolith layout. The
`agent` layer follows the import-linter contract already present;
`application/chat|agent` mirror the `application/<domain>` conventions
(contracts/ports/service); infrastructure adapters mirror
`infrastructure/criteria` (fake + managed) and `infrastructure/silver`
(testcontainers integration); the harness mirrors `check-*.ps1`.

## Planned Implementation Sequence

The later `/speckit-tasks` artifact must decompose these phases into
test-first, path-specific tasks. Each behavioral slice starts with the
failing contract/unit test named here, then the minimum implementation,
then the full gate.

### Phase A — Chat persistence foundation

- Migration `0009_langgraph_runtime` (5 tables) + `alembic/env.py`
  `include_object` filter; models `chat.py`/`agent.py`; repositories.
- `application/chat` contracts/ports/service (create/get/history/append/
  persist/mirror/limits/immutability) + ownership checks.
- Events registry update (`chat.session_created.v1`,
  `chat.message_created.v1`, version 2) + emission in the service.
- Tests: `tests/unit/application/chat/test_service.py`,
  `tests/integration/chat/test_session_repo.py`,
  `tests/migrations/test_0009_langgraph_runtime.py`,
  `tests/contract/test_agent_chat_events.py`.
- Gate: FR-001..FR-003; SC-001.

### Phase B — State schema, topology v1 and run recording

- `contracts/agent/v1/state-schema-v1.json` + `graph-topology-v1.json`.
- `agent/state.py` (JSON-safe v1 values) and `agent/graph.py`
  (`build_topology_v1` with fake gateway + memory saver: start →
  generate_reply → persist_reply, ledger helper).
- `application/agent` contracts/ports/service (record graph/node/model-call
  runs, idempotent, 0 PII).
- Tests: `tests/contract/test_agent_state_schema.py`,
  `tests/contract/test_agent_graph_topology.py`,
  `tests/unit/agent/test_state.py`, `tests/unit/agent/test_graph.py`,
  `tests/unit/application/agent/test_run_recorder.py`.
- Gate: FR-004..FR-006, FR-016..FR-018; SC-002, SC-006.

### Phase C — Model gateway

- `application/agent/ports.py` `ModelGateway`; `FakeModelGateway`;
  `ManagedModelGateway` (HTTP structured output, timeout, bounded retry,
  usage, versions); settings `AGENT_*`.
- `contracts/agent/v1/reply-schema-v1.json`.
- Tests: `tests/contract/test_agent_reply_schema.py`,
  `tests/unit/infrastructure/agent/test_managed_gateway.py`.
- Gate: FR-010..FR-012; SC-004.

### Phase D — Durable runtime: checkpointer, resume, streaming, retention

- `infrastructure/agent/checkpointer.py` (PostgresSaver factory: setup,
  autocommit/dict_row, strict msgpack; thread deletion) and
  `agent/runtime.py` (run_turn with typed events, claim via partial unique
  index, resume with `attempt+1`, ledger-based dedupe, typed
  `ChatExecutionInProgress`).
- `agent/events.py` typed events; `infrastructure/agent/purge.py` +
  scheduler maintenance registration.
- Tests: `tests/integration/agent/test_checkpointer.py`,
  `tests/integration/agent/test_runtime_e2e.py`,
  `tests/integration/agent/test_runtime_isolation.py`,
  `tests/unit/infrastructure/agent/test_purge.py`.
- Gate: FR-007..FR-009, FR-013..FR-015; SC-003, SC-005.

### Phase E — Harness, architecture and closure

- `scripts/check-agent.ps1` + registration in `check.ps1`;
  `tests/architecture/test_agent_boundaries.py`;
  `tests/contract/test_agent_harness.py`.
- Run every quickstart scenario and `.\scripts\check.ps1` from a clean
  checkout; record evidence in
  `docs/runbooks/evidence/langgraph-runtime-acceptance.md`; update
  quickstart and `runtime-local.md` if deployment docs are touched.
- Gate: FR-019/FR-020; SC-007.

## Verification Commands

Target commands after implementation:

```powershell
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic current --check-heads
uv run pytest tests/contract/test_agent_state_schema.py tests/contract/test_agent_graph_topology.py tests/contract/test_agent_reply_schema.py tests/contract/test_agent_chat_events.py tests/contract/test_agent_harness.py tests/unit/application/chat tests/unit/application/agent tests/unit/agent tests/unit/infrastructure/agent tests/integration/chat tests/integration/agent tests/migrations/test_0009_langgraph_runtime.py tests/architecture/test_agent_boundaries.py
.\scripts\check-agent.ps1
.\scripts\check.ps1
```

No success claim is based only on a mock or a skipped surface: the
resume/no-duplicate proof runs against the real Postgres checkpointer
(testcontainers) with the real partial unique index; the isolation proof
exercises the service ownership path; gateway behavior is exercised against
the managed adapter with a controlled HTTP fake; migration 0009 is verified
up and down.

## Backlog and Requirement Traceability

| Backlog item | Plan ownership | Primary evidence |
| --- | --- | --- |
| UM-H4-001 sesiones y mensajes | Phase A | chat service + repo + migration + events (FR-001..FR-003, SC-001) |
| UM-H4-002 state schema y topologia v1 | Phase B | state/topology contracts + state/graph modules (FR-004..FR-006, SC-002) |
| UM-H4-003 checkpointer Postgres | Phase D | checkpointer integration + retention purge (FR-007..FR-009, SC-003) |
| UM-H4-004 adapter de modelo | Phase C | gateway port + fake/managed + reply schema (FR-010..FR-012, SC-004) |
| UM-H4-005 streaming y reanudacion | Phase D | runtime e2e integration (FR-013..FR-015, SC-005) |
| UM-H4-006 graph runs auditables | Phase B + D | run recorder + run tables (FR-016..FR-018, SC-006) |
| Transversal (todos) | Phase A + E | events registry + harness + architecture (FR-019/FR-020, SC-007) |

Every FR maps through these rows to at least one automated check. `tasks.md`
must preserve these mappings rather than regrouping cross-cutting checks
away from their story.

## Complexity Tracking

No constitution violation is present. The only deliberate additions beyond
a naive pass are: (a) the langgraph runtime dependency pair — mandated by
the constitution and the H4 epic (R-01, rejected alternative documented);
(b) the `effects_applied` ledger in checkpointed state — required by FR-014
and the 0-duplicates clarification, with the simpler-but-not-general
alternative (DB-only dedupe) rejected in R-04; (c) the partial unique
index as the concurrency guard — required by FR-015 and the reject
clarification, with application-level locks rejected in R-06; (d) the
library-managed checkpoint tables excluded from Alembic — required by R-03
to keep drift checks green; (e) the scheduler maintenance duty for
checkpoint retention — required by FR-008 and the retention clarification,
with the RQ-job alternative rejected in R-09. All have simpler rejected
alternatives documented that would violate the spec or the constitution.
