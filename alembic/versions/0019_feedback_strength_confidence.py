"""Structured concept feedback: strength and confidence on feedback reasons (019)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_feedback_strength_confidence"
down_revision = "0018_hard_soft_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    strength_type = sa.dialects.postgresql.ENUM(
        "low", "medium", "strong",
        name="feedback_strength",
        create_type=True,
    )
    strength_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "feedback_event_reasons",
        sa.Column("strength", strength_type, nullable=True),
    )
    op.add_column(
        "feedback_event_reasons",
        sa.Column("confidence", sa.Double(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feedback_event_reasons", "confidence")
    op.drop_column("feedback_event_reasons", "strength")
    sa.dialects.postgresql.ENUM(name="feedback_strength").drop(
        op.get_bind(), checkfirst=True
    )