"""Add structured listing attributes to the active Silver contract."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_silver_listing_attributes"
down_revision = "0019_feedback_strength_confidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "silver_listings",
        sa.Column("title_text", sa.String(500), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("surface_covered_m2", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("bathrooms", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("toilettes", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("parking_spaces", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("age_years", sa.Numeric(8, 2), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("disposition", sa.String(100), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column("orientation", sa.String(100), nullable=True),
    )
    op.add_column(
        "silver_listings",
        sa.Column(
            "media_urls",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_silver_listings_surface_covered",
        "silver_listings",
        "surface_covered_m2 IS NULL OR "
        "(surface_covered_m2 > 0 AND surface_covered_m2 <= 1000000)",
    )
    op.create_check_constraint(
        "ck_silver_listings_bathrooms",
        "silver_listings",
        "bathrooms IS NULL OR (bathrooms >= 0 AND bathrooms <= 100)",
    )
    op.create_check_constraint(
        "ck_silver_listings_toilettes",
        "silver_listings",
        "toilettes IS NULL OR (toilettes >= 0 AND toilettes <= 100)",
    )
    op.create_check_constraint(
        "ck_silver_listings_parking_spaces",
        "silver_listings",
        "parking_spaces IS NULL OR (parking_spaces >= 0 AND parking_spaces <= 100)",
    )
    op.create_check_constraint(
        "ck_silver_listings_age_years",
        "silver_listings",
        "age_years IS NULL OR (age_years >= 0 AND age_years <= 1000)",
    )


def downgrade() -> None:
    for name in (
        "ck_silver_listings_age_years",
        "ck_silver_listings_parking_spaces",
        "ck_silver_listings_toilettes",
        "ck_silver_listings_bathrooms",
        "ck_silver_listings_surface_covered",
    ):
        op.drop_constraint(name, "silver_listings", type_="check")
    for name in (
        "media_urls",
        "orientation",
        "disposition",
        "age_years",
        "parking_spaces",
        "toilettes",
        "bathrooms",
        "surface_covered_m2",
        "title_text",
    ):
        op.drop_column("silver_listings", name)
