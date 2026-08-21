"""Hard/soft catalog: soft_to_hard flag on preference facts (US3)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_hard_soft_catalog"
down_revision = "0017_urban_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preference_facts",
        sa.Column(
            "soft_to_hard",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("preference_facts", "soft_to_hard")
