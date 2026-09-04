"""Persist the total size of each ordered confirmation queue."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_conversation_v5_proposal_total"
down_revision = "0023_conversation_v5_proposal_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_profile_update_proposals",
        sa.Column("queue_total", sa.Integer(), nullable=False, server_default="1"),
    )
    # Existing rows have no queue batch marker. Their persisted ordinal is the
    # only safe evidence available, so use the largest ordinal in that scope.
    op.execute(
        "UPDATE search_profile_update_proposals AS proposal SET queue_total = ranked.total "
        "FROM (SELECT session_id, search_profile_id, MAX(queue_ordinal) AS total "
        "FROM search_profile_update_proposals GROUP BY session_id, search_profile_id) AS ranked "
        "WHERE proposal.session_id = ranked.session_id "
        "AND proposal.search_profile_id = ranked.search_profile_id"
    )
    op.create_check_constraint(
        "ck_proposals_queue_total_coherent",
        "search_profile_update_proposals",
        "queue_total >= queue_ordinal",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_proposals_queue_total_coherent",
        "search_profile_update_proposals",
    )
    op.drop_column("search_profile_update_proposals", "queue_total")
