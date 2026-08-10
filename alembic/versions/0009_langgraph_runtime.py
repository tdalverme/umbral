"""Conversational runtime schema: chat sessions/messages and agent run audit tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_langgraph_runtime"
down_revision = "0008_feedback_learning"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "chat_session_state": ("active", "paused", "archived"),
        "chat_message_role": ("user", "assistant", "system"),
        "chat_message_state": ("complete",),
        "agent_run_state": (
            "pending",
            "running",
            "completed",
            "failed",
            "interrupted",
        ),
        "agent_node_kind": ("node", "tool"),
        "agent_call_state": (
            "success",
            "invalid_output",
            "timeout",
            "error",
            "retried",
        ),
    }[name]
    return postgresql.ENUM(*values, name=name, create_type=False)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind", _enum("actor_kind"), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _create_types() -> None:
    op.execute(
        "CREATE TYPE chat_session_state AS ENUM ('active', 'paused', 'archived')"
    )
    op.execute("CREATE TYPE chat_message_role AS ENUM ('user', 'assistant', 'system')")
    op.execute("CREATE TYPE chat_message_state AS ENUM ('complete')")
    op.execute(
        "CREATE TYPE agent_run_state AS ENUM "
        "('pending', 'running', 'completed', 'failed', 'interrupted')"
    )
    op.execute("CREATE TYPE agent_node_kind AS ENUM ('node', 'tool')")
    op.execute(
        "CREATE TYPE agent_call_state AS ENUM "
        "('success', 'invalid_output', 'timeout', 'error', 'retried')"
    )


def _drop_types() -> None:
    op.execute("DROP TYPE IF EXISTS agent_call_state")
    op.execute("DROP TYPE IF EXISTS agent_node_kind")
    op.execute("DROP TYPE IF EXISTS agent_run_state")
    op.execute("DROP TYPE IF EXISTS chat_message_state")
    op.execute("DROP TYPE IF EXISTS chat_message_role")
    op.execute("DROP TYPE IF EXISTS chat_session_state")


def upgrade() -> None:
    _create_types()

    op.create_table(
        "chat_sessions",
        *_audit_columns(),
        sa.Column(
            "user_id",
            _uuid(),
            sa.ForeignKey("product_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "search_profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", _enum("chat_session_state"), nullable=False),
        sa.Index("ix_chat_sessions_user_status", "user_id", "status"),
        sa.Index("ix_chat_sessions_profile", "search_profile_id"),
    )
    op.create_table(
        "agent_graph_runs",
        *_audit_columns(),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state_schema_version", sa.Integer(), nullable=False),
        sa.Column("topology_version", sa.Integer(), nullable=False),
        sa.Column("status", _enum("agent_run_state"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", _ts(), nullable=False),
        sa.Column("finished_at", _ts()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_summary", postgresql.JSONB()),
        sa.Column("token_usage", postgresql.JSONB()),
        sa.Index("ix_agent_graph_runs_session_created", "session_id", "created_at"),
        sa.Index("ix_agent_graph_runs_correlation", "correlation_id"),
    )
    op.create_index(
        "uq_agent_graph_runs_session_active",
        "agent_graph_runs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running', 'interrupted')"),
    )
    op.create_table(
        "chat_messages",
        *_audit_columns(),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", _enum("chat_message_role"), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("state", _enum("chat_message_state"), nullable=False),
        sa.Column(
            "graph_run_id",
            _uuid(),
            sa.ForeignKey("agent_graph_runs.id", ondelete="SET NULL"),
        ),
        sa.Index("ix_chat_messages_session_created", "session_id", "created_at"),
        sa.Index("ix_chat_messages_run", "graph_run_id"),
    )
    op.create_table(
        "agent_node_runs",
        *_audit_columns(),
        sa.Column(
            "graph_run_id",
            _uuid(),
            sa.ForeignKey("agent_graph_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_name", sa.String(120), nullable=False),
        sa.Column("node_kind", _enum("agent_node_kind"), nullable=False),
        sa.Column("status", _enum("agent_run_state"), nullable=False),
        sa.Column("started_at", _ts(), nullable=False),
        sa.Column("finished_at", _ts()),
        sa.Column("error_summary", postgresql.JSONB()),
        sa.Column("usage", postgresql.JSONB()),
        sa.Index("ix_agent_node_runs_run", "graph_run_id", "started_at"),
    )
    op.create_table(
        "agent_model_calls",
        *_audit_columns(),
        sa.Column(
            "graph_run_id",
            _uuid(),
            sa.ForeignKey("agent_graph_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("model_version", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("schema_version", sa.String(120), nullable=False),
        sa.Column("status", _enum("agent_call_state"), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_code", sa.String(120)),
        sa.Index("ix_agent_model_calls_run", "graph_run_id"),
        sa.Index("ix_agent_model_calls_correlation", "correlation_id"),
    )


def downgrade() -> None:
    for name in (
        "agent_model_calls",
        "agent_node_runs",
        "chat_messages",
        "agent_graph_runs",
        "chat_sessions",
    ):
        op.drop_table(name)
    _drop_types()
