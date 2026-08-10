"""Durable search-profile update proposals for the explicit tool surface (H4.2)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_agent_tools"
down_revision = "0009_langgraph_runtime"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind",
            postgresql.ENUM(
                "system", "service", "operator", name="actor_kind", create_type=False
            ),
            nullable=False,
            server_default="system",
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE TYPE proposal_state AS ENUM ('pending', 'approved', 'rejected')")
    op.create_table(
        "search_profile_update_proposals",
        *_audit_columns(),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "search_profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("base_profile_version", sa.Integer(), nullable=False),
        sa.Column("diff", postgresql.JSONB(), nullable=False),
        sa.Column("impact", postgresql.JSONB(), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(
                "pending", "approved", "rejected", name="proposal_state", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("expires_at", _ts(), nullable=False),
        sa.Column("applied_idempotency_key", sa.String(128)),
        sa.Column("rejection_reason", sa.String(32)),
        sa.Column("applied_profile_version", sa.Integer()),
        sa.Column("applied_run_id", _uuid()),
        sa.Index("ix_proposals_profile", "search_profile_id", "state"),
        sa.Index("ix_proposals_session", "session_id"),
    )
    op.create_index(
        "uq_proposals_profile_idempotency",
        "search_profile_update_proposals",
        ["search_profile_id", "applied_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("applied_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_proposals_profile_idempotency", table_name="search_profile_update_proposals"
    )
    op.drop_table("search_profile_update_proposals")
    op.execute("DROP TYPE IF EXISTS proposal_state")
