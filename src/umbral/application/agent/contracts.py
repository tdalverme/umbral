"""Pure values for auditable agent graph runs, node runs and model calls (H4.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

RunStatus = Literal["pending", "running", "completed", "failed", "interrupted"]
NodeKind = Literal["node", "tool"]
CallStatus = Literal["success", "invalid_output", "timeout", "error", "retried"]


@dataclass(frozen=True, slots=True)
class GraphRun:
    """One graph run; its id doubles as the LangGraph thread id."""

    run_id: UUID
    session_id: UUID
    state_schema_version: int
    topology_version: int
    status: RunStatus
    attempt: int
    correlation_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    latency_ms: int | None = None
    error_summary: Mapping[str, object] | None = None
    token_usage: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class NodeRun:
    """One node (or later tool) execution inside a graph run."""

    node_run_id: UUID
    graph_run_id: UUID
    node_name: str
    node_kind: NodeKind
    status: RunStatus
    correlation_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: Mapping[str, object] | None = None
    usage: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ModelCall:
    """One model call with immutable model/prompt/schema versions and usage."""

    call_id: UUID
    graph_run_id: UUID | None
    model_version: str
    prompt_version: str
    schema_version: str
    status: CallStatus
    correlation_id: UUID
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ModelResult:
    """A validated structured model response with usage and status."""

    content: Mapping[str, object] | None
    model_version: str
    status: CallStatus
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    error_code: str | None = None


class AgentError(Exception):
    """Base class for sanitized agent failures."""

    code = "agent.error"


class AgentRunNotFound(AgentError):
    """No resumable run exists for the session."""

    code = "agent.run_not_found"


class AgentStateIncompatible(AgentError):
    """A checkpoint state schema cannot be resumed."""

    code = "agent.state_incompatible"
