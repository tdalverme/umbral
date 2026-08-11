"""Notification preferences, decisions and inbox (H5).

Adds `notification_preferences` (versioned per-user/search settings),
`notification_decisions` (deterministic planner decisions with dedupe via a
partial unique index) and `notification_inbox_items` (web view 1:1 with the
decision). Delivery reuses the durable job runtime; no outbox table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_notifications"
down_revision = "0012_agent_evals"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _create_types() -> None:
    op.execute(
        "CREATE TYPE notification_trigger AS ENUM ('new_match', 'price_drop')"
    )
    op.execute(
        "CREATE TYPE notification_decision_state AS ENUM "
        "('pending_delivery', 'pending_digest', 'postponed', 'duplicated', "
        "'discarded', 'delivered', 'read', 'acted')"
    )
    op.execute(
        "CREATE TYPE notification_pref_state AS ENUM "
        "('active', 'paused', 'disabled')"
    )


def _drop_types() -> None:
    op.execute("DROP TYPE IF EXISTS notification_pref_state")
    op.execute("DROP TYPE IF EXISTS notification_decision_state")
    op.execute("DROP TYPE IF EXISTS notification_trigger")


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
    _create_types()
    op.create_table(
        "notification_preferences",
        *_audit_columns(),
        sa.Column("user_id", _uuid(), sa.ForeignKey("product_users.id"), nullable=False),
        sa.Column(
            "search_profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id"),
            nullable=False,
        ),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("inbox_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("quiet_hours_start", sa.Time(), nullable=False),
        sa.Column("quiet_hours_end", sa.Time(), nullable=False),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("digest_local_hour", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("score_threshold", sa.Numeric(6, 4), nullable=False),
        sa.Column("state", postgresql.ENUM("active", "paused", "disabled",
            name="notification_pref_state", create_type=False), nullable=False),
        sa.Index("ix_notification_prefs_user", "user_id"),
        sa.Index("ix_notification_prefs_search", "search_profile_id"),
    )
    op.create_table(
        "notification_decisions",
        *_audit_columns(),
        sa.Column("user_id", _uuid(), sa.ForeignKey("product_users.id"), nullable=False),
        sa.Column(
            "search_profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id"),
            nullable=False,
        ),
        sa.Column(
            "recommendation_item_id",
            _uuid(),
            sa.ForeignKey("recommendation_items.id"),
            nullable=False,
        ),
        sa.Column("trigger", postgresql.ENUM("new_match", "price_drop",
            name="notification_trigger", create_type=False), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("reason_detail", sa.String(500), nullable=True),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("preferences_version", sa.Integer(), nullable=False),
        sa.Column("price_before", sa.Numeric(18, 2), nullable=True),
        sa.Column("price_after", sa.Numeric(18, 2), nullable=True),
        sa.Column("decision_state", postgresql.ENUM("pending_delivery",
            "pending_digest", "postponed", "duplicated", "discarded",
            "delivered", "read", "acted", name="notification_decision_state",
            create_type=False), nullable=False),
        sa.Column("duplicate_of_id", _uuid(), nullable=True),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Index("ix_notification_decisions_user_created", "user_id", "created_at"),
        sa.Index("ix_notification_decisions_state_digest", "decision_state"),
        sa.Index(
            "uq_notification_decision_item_trigger",
            "recommendation_item_id",
            "trigger",
            unique=True,
            postgresql_where=sa.text(
                "decision_state IN "
                "('pending_delivery', 'pending_digest', 'postponed', "
                "'delivered', 'read', 'acted')"
            ),
        ),
    )
    op.create_table(
        "notification_inbox_items",
        *_audit_columns(),
        sa.Column(
            "decision_id",
            _uuid(),
            sa.ForeignKey("notification_decisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", _uuid(), sa.ForeignKey("product_users.id"), nullable=False),
        sa.Column("read_at", _ts(), nullable=True),
        sa.Column("acted_at", _ts(), nullable=True),
        sa.UniqueConstraint("decision_id"),
        sa.Index("ix_notification_inbox_user_created", "user_id", "created_at"),
    )


def downgrade() -> None:
    op.drop_table("notification_inbox_items")
    op.drop_table("notification_decisions")
    op.drop_table("notification_preferences")
    _drop_types()
