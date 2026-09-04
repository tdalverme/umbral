"""Persist ordered V5 hard-filter confirmation proposals.

The queue position and originating typed act must survive process restarts and
proposal supersession, so they cannot be inferred safely from JSON payloads or
timestamps.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_conversation_v5_proposal_queue"
down_revision = "0022_conversation_v5_command_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_profile_update_proposals",
        sa.Column("source_act_id", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column(
        "search_profile_update_proposals",
        sa.Column("queue_ordinal", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_proposals_session_queue",
        "search_profile_update_proposals",
        ["session_id", "state", "queue_ordinal"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposals_session_queue", table_name="search_profile_update_proposals")
    op.drop_column("search_profile_update_proposals", "queue_ordinal")
    op.drop_column("search_profile_update_proposals", "source_act_id")
