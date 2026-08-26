"""Persist V5 conversation command receipts for idempotent execution."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_conversation_v5_command_receipts"
down_revision = "0021_urban_derived_consistency"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    receipt_state = postgresql.ENUM(
        "started",
        "applied",
        "failed",
        name="conversation_v5_receipt_state",
        create_type=False,
    )
    receipt_state.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "conversation_v5_command_receipts",
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("session_id", _uuid(), nullable=False),
        sa.Column("message_id", _uuid(), nullable=False),
        sa.Column("act_id", sa.String(64), nullable=False),
        sa.Column("command_kind", sa.String(40), nullable=False),
        sa.Column("status", receipt_state, nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_v5_receipts_session",
        "conversation_v5_command_receipts",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_v5_receipts_session",
        table_name="conversation_v5_command_receipts",
    )
    op.drop_table("conversation_v5_command_receipts")
    op.execute("DROP TYPE IF EXISTS conversation_v5_receipt_state")
