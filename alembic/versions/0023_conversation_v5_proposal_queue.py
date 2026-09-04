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
        sa.Column("source_act_id", sa.String(length=120), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "search_profile_update_proposals",
        sa.Column("queue_ordinal", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(
        "UPDATE search_profile_update_proposals SET source_act_id = 'legacy' "
        "WHERE source_act_id = ''"
    )
    op.execute(
        "UPDATE search_profile_update_proposals SET queue_ordinal = ranked.ordinal "
        "FROM (SELECT id, row_number() OVER (PARTITION BY session_id "
        "ORDER BY created_at, id) AS ordinal FROM search_profile_update_proposals "
        "WHERE state = 'pending') AS ranked "
        "WHERE search_profile_update_proposals.id = ranked.id"
    )
    op.create_index(
        "ix_proposals_session_queue",
        "search_profile_update_proposals",
        ["session_id", "state", "queue_ordinal"],
    )
    op.create_check_constraint(
        "ck_proposals_queue_ordinal_positive", "search_profile_update_proposals",
        "queue_ordinal >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_proposals_queue_ordinal_positive", "search_profile_update_proposals")
    op.drop_index("ix_proposals_session_queue", table_name="search_profile_update_proposals")
    op.drop_column("search_profile_update_proposals", "queue_ordinal")
    op.drop_column("search_profile_update_proposals", "source_act_id")
