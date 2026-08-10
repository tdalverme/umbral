"""Idempotent chat send and interactive proposal transitions (H4.3).

Adds `chat_messages.client_message_id` with a partial unique index (idempotent
send, R-06) and `search_profile_update_proposals.rejection_note` +
`superseded_by_proposal_id` (interactive reject/edited chain, R-05).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_chat_streaming"
down_revision = "0010_agent_tools"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("client_message_id", _uuid(), nullable=True),
    )
    op.create_index(
        "uq_chat_messages_session_client",
        "chat_messages",
        ["session_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )
    op.add_column(
        "search_profile_update_proposals",
        sa.Column("rejection_note", sa.String(200), nullable=True),
    )
    op.add_column(
        "search_profile_update_proposals",
        sa.Column(
            "superseded_by_proposal_id",
            _uuid(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_proposals_superseded_by",
        "search_profile_update_proposals",
        ["superseded_by_proposal_id"],
    )
    op.create_foreign_key(
        "fk_proposals_superseded_by",
        "search_profile_update_proposals",
        "search_profile_update_proposals",
        ["superseded_by_proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_proposals_superseded_by",
        "search_profile_update_proposals",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_proposals_superseded_by",
        table_name="search_profile_update_proposals",
    )
    op.drop_column("search_profile_update_proposals", "superseded_by_proposal_id")
    op.drop_column("search_profile_update_proposals", "rejection_note")
    op.drop_index("uq_chat_messages_session_client", table_name="chat_messages")
    op.drop_column("chat_messages", "client_message_id")
