"""Structured search radar schema: profiles, versions, runs, items, events."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_search_radar"
down_revision = "0004_silver_normalization"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "search_profile_state": ("active", "paused", "archived"),
        "recommendation_run_state": ("pending", "running", "succeeded", "failed"),
        "recommendation_run_trigger": ("created", "edited", "resumed"),
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
        "CREATE TYPE search_profile_state AS ENUM ('active', 'paused', 'archived')"
    )
    op.execute(
        "CREATE TYPE recommendation_run_state AS ENUM "
        "('pending', 'running', 'succeeded', 'failed')"
    )
    op.execute(
        "CREATE TYPE recommendation_run_trigger AS ENUM "
        "('created', 'edited', 'resumed')"
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    _create_types()

    op.create_table(
        "search_profiles",
        *_audit_columns(),
        sa.Column(
            "owner_id",
            _uuid(),
            sa.ForeignKey("product_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("zones", postgresql.JSONB(), nullable=False),
        sa.Column("budget_max", sa.Numeric(18, 2), nullable=False),
        sa.Column("budget_min", sa.Numeric(18, 2)),
        sa.Column("min_rooms", sa.Integer(), nullable=False),
        sa.Column("surface_min", sa.Numeric(12, 2)),
        sa.Column("surface_max", sa.Numeric(12, 2)),
        sa.Column("status", _enum("search_profile_state"), nullable=False),
        sa.Column("unknown_strategy", postgresql.JSONB(), nullable=False),
        sa.Column("current_version_id", _uuid()),
        sa.Column("latest_run_id", _uuid()),
        sa.UniqueConstraint("owner_id", "name", name="uq_search_profiles_owner_name"),
        sa.CheckConstraint(
            "budget_max > 0 AND (budget_min IS NULL OR budget_min < budget_max)",
            name="ck_search_profiles_budget",
        ),
        sa.CheckConstraint(
            "surface_min >= 0 AND (surface_max IS NULL OR surface_max > surface_min)",
            name="ck_search_profiles_surface",
        ),
        sa.CheckConstraint(
            "min_rooms >= 0 AND min_rooms <= 200",
            name="ck_search_profiles_rooms",
        ),
        sa.Index("ix_search_profiles_owner_status", "owner_id", "status"),
        sa.Index("ix_search_profiles_owner_created", "owner_id", "created_at"),
    )

    op.create_table(
        "search_profile_versions",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "profile_id",
            "profile_version",
            name="uq_search_profile_versions_profile_version",
        ),
        sa.CheckConstraint(
            "profile_version >= 1",
            name="ck_search_profile_versions_profile_version",
        ),
    )

    op.create_table(
        "recommendation_runs",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profile_version_id",
            _uuid(),
            sa.ForeignKey("search_profile_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", _enum("recommendation_run_state"), nullable=False),
        sa.Column("trigger", _enum("recommendation_run_trigger"), nullable=False),
        sa.Column("score_policy_version", sa.String(100), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "published_item_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("job_execution_id", _uuid()),
        sa.Column("finished_at", _ts()),
        sa.UniqueConstraint(
            "profile_id",
            "profile_version_id",
            "trigger",
            name="uq_recommendation_runs_profile_version",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'succeeded', 'failed')"
            " AND (state IN ('pending', 'running') OR finished_at IS NOT NULL)",
            name="ck_recommendation_runs_state_finished",
        ),
        sa.Index("ix_recommendation_runs_profile_state", "profile_id", "state"),
        sa.Index("ix_recommendation_runs_profile_created", "profile_id", "created_at"),
        sa.Index("ix_recommendation_runs_profile_version", "profile_version_id"),
    )

    op.create_table(
        "recommendation_items",
        *_audit_columns(),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("recommendation_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(6, 4), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("contributions", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "run_id", "position", name="uq_recommendation_items_run_position"
        ),
        sa.UniqueConstraint(
            "run_id", "listing_id", name="uq_recommendation_items_run_listing"
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1", name="ck_recommendation_items_score"
        ),
        sa.CheckConstraint("position >= 0", name="ck_recommendation_items_position"),
        sa.Index("ix_recommendation_items_run_position", "run_id", "position"),
        sa.Index("ix_recommendation_items_listing", "listing_id"),
    )

    op.create_table(
        "product_events",
        *_audit_columns(),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("occurred_at", _ts(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "event_type ~ '^[a-z][a-z0-9_.]{0,99}$'",
            name="ck_product_events_type",
        ),
        sa.Index("ix_product_events_type_occurred", "event_type", "occurred_at"),
        sa.Index("ix_product_events_occurred", "occurred_at"),
        sa.Index("ix_product_events_actor", "actor_id"),
    )

    op.execute(
        "ALTER TABLE search_profiles ADD CONSTRAINT "
        "fk_search_profiles_current_version_id_search_profile_versions "
        "FOREIGN KEY (current_version_id) REFERENCES search_profile_versions (id) "
        "ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE search_profiles ADD CONSTRAINT "
        "fk_search_profiles_latest_run_id_recommendation_runs "
        "FOREIGN KEY (latest_run_id) REFERENCES recommendation_runs (id) "
        "ON DELETE RESTRICT"
    )


def downgrade() -> None:
    op.drop_table("product_events")
    op.drop_table("recommendation_items")
    op.drop_table("recommendation_runs")
    op.drop_table("search_profiles")
    op.drop_table("search_profile_versions")
    op.execute("DROP TYPE recommendation_run_trigger")
    op.execute("DROP TYPE recommendation_run_state")
    op.execute("DROP TYPE search_profile_state")
