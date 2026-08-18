"""Declarative urban signals: contracts, snapshots, primitives and observations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_urban_signals"
down_revision = "0016_conversational_search_copilot"
branch_labels = None
depends_on = None

_DOWNGRADE_REFUSAL = "0017 downgrade would discard urban signal data"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _actor_kind() -> postgresql.ENUM:
    return postgresql.ENUM(name="actor_kind", create_type=False)


def _geometry() -> object:
    from geoalchemy2 import Geometry

    return Geometry(geometry_type="POINT", srid=4326)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind", _actor_kind(), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _add_urban_kind() -> None:
    op.execute("ALTER TYPE extraction_kind ADD VALUE IF NOT EXISTS 'urban'")


def _create_urban_tables() -> None:
    op.create_table(
        "urban_contracts",
        *_audit_columns(),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("superseded_by", _uuid(), nullable=True),
        sa.UniqueConstraint(
            "contract_version", name="uq_urban_contracts_version"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')", name="ck_urban_contracts_status"
        ),
        sa.CheckConstraint(
            "pg_column_size(payload::text) <= 65536",
            name="ck_urban_contracts_payload_size",
        ),
    )
    op.create_table(
        "urban_snapshots",
        *_audit_columns(),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("data_date", _ts()),
        sa.Column("status", sa.String(20), nullable=False, server_default="importing"),
        sa.Column("poi_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linear_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "status IN ('importing', 'ready', 'failed')",
            name="ck_urban_snapshots_status",
        ),
    )
    op.create_index(
        "ix_urban_snapshots_status_created", "urban_snapshots", ["status", "created_at"]
    )
    op.create_table(
        "urban_categories",
        *_audit_columns(),
        sa.Column("snapshot_id", _uuid(), nullable=False),
        sa.Column("osm_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("geometry", _geometry()),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["urban_snapshots.id"],
            name="fk_urban_categories_snapshot_id_urban_snapshots",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "snapshot_id", "osm_id", "category", name="uq_urban_categories_snapshot_osm"
        ),
        sa.CheckConstraint(
            "kind IN ('poi', 'linear')", name="ck_urban_categories_kind"
        ),
    )
    op.create_index(
        "ix_urban_categories_snapshot_kind", "urban_categories", ["snapshot_id", "kind"]
    )
    op.create_index("ix_urban_categories_category", "urban_categories", ["category"])
    op.execute(
        "CREATE INDEX ix_urban_categories_snapshot_geom "
        "ON urban_categories USING gist (geometry)"
    )
    op.create_table(
        "urban_primitives",
        *_audit_columns(),
        sa.Column("listing_id", _uuid(), nullable=False),
        sa.Column("snapshot_id", _uuid(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("count_300m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("count_600m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nearest_m", sa.Float()),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["silver_listings.id"],
            name="fk_urban_primitives_listing_id_silver_listings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["urban_snapshots.id"],
            name="fk_urban_primitives_snapshot_id_urban_snapshots",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "listing_id",
            "snapshot_id",
            "category",
            name="uq_urban_primitives_listing_snapshot_category",
        ),
        sa.CheckConstraint(
            "kind IN ('poi', 'linear')", name="ck_urban_primitives_kind"
        ),
    )
    op.create_index(
        "ix_urban_primitives_listing_snapshot",
        "urban_primitives",
        ["listing_id", "snapshot_id"],
    )
    op.create_index("ix_urban_primitives_category", "urban_primitives", ["category"])
    op.create_table(
        "urban_signals",
        *_audit_columns(),
        sa.Column("listing_id", _uuid(), nullable=False),
        sa.Column("snapshot_id", _uuid(), nullable=False),
        sa.Column("contract_version_id", _uuid(), nullable=False),
        sa.Column("signal", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("normalized_value", sa.Float()),
        sa.Column(
            "normalization_scope",
            sa.String(20),
            nullable=False,
            server_default="barrio",
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("missing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("contributors", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["silver_listings.id"],
            name="fk_urban_signals_listing_id_silver_listings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["urban_snapshots.id"],
            name="fk_urban_signals_snapshot_id_urban_snapshots",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contract_version_id"],
            ["urban_contracts.id"],
            name="fk_urban_signals_contract_version_id_urban_contracts",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "listing_id",
            "contract_version_id",
            "signal",
            name="uq_urban_signals_listing_contract_signal",
        ),
        sa.CheckConstraint(
            "value >= 0 AND value <= 1", name="ck_urban_signals_value"
        ),
        sa.CheckConstraint(
            "normalized_value IS NULL OR "
            "(normalized_value >= 0 AND normalized_value <= 1)",
            name="ck_urban_signals_normalized_value",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_urban_signals_confidence"
        ),
        sa.CheckConstraint(
            "normalization_scope IN ('barrio', 'caba')",
            name="ck_urban_signals_scope",
        ),
    )
    op.create_index(
        "ix_urban_signals_listing_contract",
        "urban_signals",
        ["listing_id", "contract_version_id"],
    )
    op.create_index("ix_urban_signals_snapshot", "urban_signals", ["snapshot_id"])
    op.create_index("ix_urban_signals_signal", "urban_signals", ["signal"])
    op.create_table(
        "neighborhood_signal_stats",
        *_audit_columns(),
        sa.Column("snapshot_id", _uuid(), nullable=False),
        sa.Column("barrio", sa.String(100), nullable=False),
        sa.Column("signal", sa.String(100), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("normalization_scope", sa.String(20), nullable=False),
        sa.Column("p50", sa.Float()),
        sa.Column("p75", sa.Float()),
        sa.Column("p90", sa.Float()),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["urban_snapshots.id"],
            name="fk_neighborhood_stats_snapshot_id_urban_snapshots",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "barrio",
            "signal",
            name="uq_neighborhood_stats_snapshot_barrio_signal",
        ),
        sa.CheckConstraint(
            "normalization_scope IN ('barrio', 'caba')",
            name="ck_neighborhood_stats_scope",
        ),
        sa.CheckConstraint(
            "sample_size >= 0", name="ck_neighborhood_stats_sample_size"
        ),
    )
    op.create_index(
        "ix_neighborhood_stats_barrio_signal",
        "neighborhood_signal_stats",
        ["barrio", "signal"],
    )


def upgrade() -> None:
    _add_urban_kind()
    # Replace the previous fixed-type urban_signals table with the declarative
    # model. The old pipeline (cafe/transport/green_space rows) is superseded.
    op.drop_table("urban_signals")
    _create_urban_tables()


def _downgrade_would_discard_data() -> bool:
    connection = op.get_bind()
    return bool(
        connection.scalar(
            sa.text(
                """SELECT EXISTS (SELECT 1 FROM urban_signals) OR
                          EXISTS (SELECT 1 FROM urban_snapshots) OR
                          EXISTS (SELECT 1 FROM urban_contracts)"""
            )
        )
    )


def _restore_legacy_urban_signals() -> None:
    """Recreate the previous fixed-type urban_signals table (from 0006)."""
    from geoalchemy2 import Geometry

    op.create_table(
        "urban_signals",
        *_audit_columns(),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("signal_source", sa.String(100), nullable=False),
        sa.Column("observed_at", _ts(), nullable=False),
        sa.Column(
            "geometry",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "signal_type IN ('cafe', 'transport', 'green_space')",
            name="ck_urban_signals_signal_type",
        ),
        sa.Index("ix_urban_signals_listing", "listing_id"),
        sa.Index("ix_urban_signals_type_observed", "signal_type", "observed_at"),
    )


def downgrade() -> None:
    if _downgrade_would_discard_data():
        raise RuntimeError(_DOWNGRADE_REFUSAL)
    op.drop_table("neighborhood_signal_stats")
    op.drop_table("urban_signals")
    op.drop_table("urban_primitives")
    op.drop_table("urban_categories")
    op.drop_table("urban_snapshots")
    op.drop_table("urban_contracts")
    _restore_legacy_urban_signals()
    # The enum value 'urban' is additive; PostgreSQL cannot remove it safely
    # without recreating the type, so downgrade leaves the value in place.
