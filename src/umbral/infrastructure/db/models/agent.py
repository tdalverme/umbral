"""Auditable agent graph runs, node runs and model calls (H4.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

AGENT_RUN_STATE = ENUM(
    "pending",
    "running",
    "completed",
    "failed",
    "interrupted",
    name="agent_run_state",
    create_type=True,
)
AGENT_NODE_KIND = ENUM("node", "tool", name="agent_node_kind", create_type=True)
AGENT_CALL_STATE = ENUM(
    "success",
    "invalid_output",
    "timeout",
    "error",
    "retried",
    name="agent_call_state",
    create_type=True,
)

_ACTIVE_RUNS = "status IN ('pending', 'running', 'interrupted')"


class AgentGraphRun(IdentityAuditMixin, Base):
    """One graph run; the row id doubles as the LangGraph thread id."""

    __tablename__ = "agent_graph_runs"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index(
            "uq_agent_graph_runs_session_active",
            "session_id",
            unique=True,
            postgresql_where=text(_ACTIVE_RUNS),
        ),
        Index("ix_agent_graph_runs_session_created", "session_id", "created_at"),
        Index("ix_agent_graph_runs_correlation", "correlation_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    topology_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(AGENT_RUN_STATE, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    token_usage: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class AgentNodeRun(IdentityAuditMixin, Base):
    """One node (or later tool) execution inside a graph run."""

    __tablename__ = "agent_node_runs"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (Index("ix_agent_node_runs_run", "graph_run_id", "started_at"),)

    graph_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_graph_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    node_kind: Mapped[str] = mapped_column(AGENT_NODE_KIND, nullable=False)
    status: Mapped[str] = mapped_column(AGENT_RUN_STATE, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    usage: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class AgentModelCall(IdentityAuditMixin, Base):
    """One model call with immutable versions and usage."""

    __tablename__ = "agent_model_calls"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index("ix_agent_model_calls_run", "graph_run_id"),
        Index("ix_agent_model_calls_correlation", "correlation_id"),
    )

    graph_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_graph_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_version: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(AGENT_CALL_STATE, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
