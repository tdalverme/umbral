"""Silver normalization schema: canonical properties, listings, dedupe, changes."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0004_silver_normalization"
down_revision = "0003_bronze_ingestion"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "canonical_state": ("active",),
        "operation_type": ("rental",),
        "property_type": (
            "apartment",
            "house",
            "room",
            "studio",
            "commercial",
            "other",
        ),
        "currency_type": ("ARS", "USD"),
        "geo_precision": ("exact", "block", "neighborhood", "approximate", "unknown"),
        "dedupe_method": ("deterministic", "proposal"),
        "dedupe_link_state": ("pending", "confirmed", "rejected"),
        "change_type": ("price", "text", "attribute", "status"),
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
    op.execute("CREATE TYPE canonical_state AS ENUM ('active')")
    op.execute("CREATE TYPE operation_type AS ENUM ('rental')")
    op.execute(
        "CREATE TYPE property_type AS ENUM "
        "('apartment', 'house', 'room', 'studio', 'commercial', 'other')"
    )
    op.execute("CREATE TYPE currency_type AS ENUM ('ARS', 'USD')")
    op.execute(
        "CREATE TYPE geo_precision AS ENUM "
        "('exact', 'block', 'neighborhood', 'approximate', 'unknown')"
    )
    op.execute("CREATE TYPE dedupe_method AS ENUM ('deterministic', 'proposal')")
    op.execute(
        "CREATE TYPE dedupe_link_state AS ENUM ('pending', 'confirmed', 'rejected')"
    )
    op.execute(
        "CREATE TYPE change_type AS ENUM ('price', 'text', 'attribute', 'status')"
    )


def upgrade() -> None:
    _create_types()

    op.create_table(
        "canonical_properties",
        *_audit_columns(),
        sa.Column("state", _enum("canonical_state"), nullable=False),
        sa.Column("first_seen_at", _ts(), nullable=False),
        sa.Column("latest_listing_id", _uuid()),
        sa.CheckConstraint("state IN ('active')", name="ck_canonical_properties_state"),
    )

    op.create_table(
        "silver_listings",
        *_audit_columns(),
        sa.Column(
            "canonical_property_id",
            _uuid(),
            sa.ForeignKey("canonical_properties.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("import_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            _uuid(),
            sa.ForeignKey("raw_listing_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_version", sa.String(100), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("url", sa.String(2000)),
        sa.Column("published_at", _ts()),
        sa.Column("last_observed_at", _ts(), nullable=False),
        sa.Column("normalizer_version", sa.String(100), nullable=False),
        sa.Column("operation", _enum("operation_type"), nullable=False),
        sa.Column("property_type", _enum("property_type"), nullable=False),
        sa.Column("price_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("price_currency", _enum("currency_type"), nullable=False),
        sa.Column("expenses_value", sa.Numeric(18, 2)),
        sa.Column("expenses_currency", _enum("currency_type")),
        sa.Column("total_cost", sa.Numeric(18, 2), nullable=False),
        sa.Column("price_assumptions", postgresql.JSONB(), nullable=False),
        sa.Column("surface_m2", sa.Numeric(12, 2)),
        sa.Column("rooms", sa.Integer()),
        sa.Column("bedrooms", sa.Integer()),
        sa.Column("floor", sa.Integer()),
        sa.Column("amenities", postgresql.JSONB(), nullable=False),
        sa.Column("description_text", sa.String(20000)),
        sa.Column("location_text", sa.String(500), nullable=False),
        sa.Column("neighborhood", sa.String(200)),
        sa.Column("geo_precision", _enum("geo_precision"), nullable=False),
        sa.Column("geometry", Geometry(geometry_type="POINT", srid=4326)),
        sa.Column("geo_source", sa.String(100)),
        sa.Column("normalization_errors", postgresql.JSONB(), nullable=False),
        sa.Column("captured_at", _ts(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "normalizer_version",
            name="uq_silver_listings_snapshot_version",
        ),
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            "captured_at",
            "normalizer_version",
            name="uq_silver_listings_source_external_captured",
        ),
        sa.CheckConstraint("price_value > 0", name="ck_silver_listings_price"),
        sa.CheckConstraint("total_cost > 0", name="ck_silver_listings_total_cost"),
        sa.CheckConstraint(
            "expenses_value >= 0 OR expenses_value IS NULL",
            name="ck_silver_listings_expenses",
        ),
        sa.CheckConstraint(
            "surface_m2 IS NULL OR (surface_m2 > 0 AND surface_m2 <= 1000000)",
            name="ck_silver_listings_surface",
        ),
        sa.CheckConstraint(
            "rooms IS NULL OR (rooms >= 0 AND rooms <= 200)",
            name="ck_silver_listings_rooms",
        ),
        sa.CheckConstraint(
            "bedrooms IS NULL OR (bedrooms >= 0 AND bedrooms <= 100)",
            name="ck_silver_listings_bedrooms",
        ),
        sa.CheckConstraint(
            "floor IS NULL OR (floor >= -10 AND floor <= 1000)",
            name="ck_silver_listings_floor",
        ),
    )
    op.create_index(
        "ix_silver_listings_canonical_captured",
        "silver_listings",
        ["canonical_property_id", "captured_at"],
    )
    op.create_index(
        "ix_silver_listings_source_external_captured_idx",
        "silver_listings",
        ["source_id", "external_id", "captured_at"],
    )
    op.create_index(
        "ix_silver_listings_geo_precision", "silver_listings", ["geo_precision"]
    )
    op.create_index(
        "ix_silver_listings_operation_type_currency",
        "silver_listings",
        ["operation", "property_type", "price_currency"],
    )

    op.create_table(
        "dedupe_links",
        *_audit_columns(),
        sa.Column(
            "listing_a_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "listing_b_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("method", _enum("dedupe_method"), nullable=False),
        sa.Column("state", _enum("dedupe_link_state"), nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("score", sa.Numeric(5, 4)),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("decided_by", sa.String(128)),
        sa.Column("decided_at", _ts()),
        sa.UniqueConstraint(
            "listing_a_id", "listing_b_id", name="uq_dedupe_links_pair"
        ),
        sa.CheckConstraint(
            "listing_a_id < listing_b_id", name="ck_dedupe_links_pair_order"
        ),
        sa.CheckConstraint(
            "(method = 'deterministic' AND state = 'confirmed') OR "
            "(method = 'proposal')",
            name="ck_dedupe_links_state_method",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name="ck_dedupe_links_score",
        ),
    )
    op.create_index("ix_dedupe_links_state", "dedupe_links", ["state"])

    op.create_table(
        "listing_changes",
        *_audit_columns(),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("previous_listing_id", _uuid()),
        sa.Column("change_type", _enum("change_type"), nullable=False),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=False),
        sa.Column("after", postgresql.JSONB(), nullable=False),
        sa.Column("origin", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("listing_id", "field", name="uq_listing_changes_field"),
    )
    op.create_index(
        "ix_listing_changes_previous", "listing_changes", ["previous_listing_id"]
    )
    op.create_index(
        "ix_listing_changes_type_created",
        "listing_changes",
        ["change_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("listing_changes")
    op.drop_table("dedupe_links")
    op.drop_table("silver_listings")
    op.drop_table("canonical_properties")
    op.execute("DROP TYPE IF EXISTS change_type")
    op.execute("DROP TYPE IF EXISTS dedupe_link_state")
    op.execute("DROP TYPE IF EXISTS dedupe_method")
    op.execute("DROP TYPE IF EXISTS geo_precision")
    op.execute("DROP TYPE IF EXISTS currency_type")
    op.execute("DROP TYPE IF EXISTS property_type")
    op.execute("DROP TYPE IF EXISTS operation_type")
    op.execute("DROP TYPE IF EXISTS canonical_state")
