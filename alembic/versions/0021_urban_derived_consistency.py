"""Make Urban derived data metric- and snapshot-consistent."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision = "0021_urban_derived_consistency"
down_revision = "0020_silver_listing_attributes"
branch_labels = None
depends_on = None

_COUNT_300_CATEGORIES = (
    "supermarket",
    "convenience",
    "pharmacy",
    "health",
    "cafe",
    "nightlife",
    "restaurant",
    "bus_stop",
    "gym",
)
_COUNT_600_CATEGORIES = _COUNT_300_CATEGORIES + (
    "subway_station",
    "green_space",
    "school",
    "cinema",
    "library",
    "theatre",
    "bicycle_parking",
)


def _urban_data_exists() -> bool:
    connection = op.get_bind()
    return bool(
        connection.scalar(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM urban_categories) OR "
                "EXISTS (SELECT 1 FROM urban_primitives) OR "
                "EXISTS (SELECT 1 FROM urban_signals) OR "
                "EXISTS (SELECT 1 FROM neighborhood_signal_stats)"
            )
        )
    )


def _in_list(categories: tuple[str, ...]) -> str:
    return ", ".join(f"'{category}'" for category in categories)


def upgrade() -> None:
    op.alter_column(
        "urban_categories",
        "geometry",
        existing_type=Geometry(geometry_type="POINT", srid=4326),
        type_=Geometry(geometry_type="GEOMETRY", srid=4326),
        existing_nullable=True,
        postgresql_using="geometry::geometry(GEOMETRY,4326)",
    )
    for column in ("count_300m", "count_600m"):
        op.alter_column(
            "urban_primitives",
            column,
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )

    op.execute(
        sa.text(
            "UPDATE urban_primitives SET count_300m = NULL "
            f"WHERE category NOT IN ({_in_list(_COUNT_300_CATEGORIES)})"
        )
    )
    op.execute(
        sa.text(
            "UPDATE urban_primitives SET count_600m = NULL "
            f"WHERE category NOT IN ({_in_list(_COUNT_600_CATEGORIES)})"
        )
    )

    op.drop_constraint(
        "uq_urban_signals_listing_contract_signal",
        "urban_signals",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_urban_signals_listing_snapshot_contract_signal",
        "urban_signals",
        ["listing_id", "snapshot_id", "contract_version_id", "signal"],
    )
    op.drop_index("ix_urban_signals_listing_contract", table_name="urban_signals")
    op.create_index(
        "ix_urban_signals_listing_contract",
        "urban_signals",
        ["listing_id", "snapshot_id", "contract_version_id"],
    )


def downgrade() -> None:
    if _urban_data_exists():
        raise RuntimeError("0021 downgrade would discard urban derived data")

    op.drop_index("ix_urban_signals_listing_contract", table_name="urban_signals")
    op.create_index(
        "ix_urban_signals_listing_contract",
        "urban_signals",
        ["listing_id", "contract_version_id"],
    )
    op.drop_constraint(
        "uq_urban_signals_listing_snapshot_contract_signal",
        "urban_signals",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_urban_signals_listing_contract_signal",
        "urban_signals",
        ["listing_id", "contract_version_id", "signal"],
    )
    for column in ("count_300m", "count_600m"):
        op.alter_column(
            "urban_primitives",
            column,
            existing_type=sa.Integer(),
            nullable=False,
            server_default="0",
        )
    op.alter_column(
        "urban_categories",
        "geometry",
        existing_type=Geometry(geometry_type="GEOMETRY", srid=4326),
        type_=Geometry(geometry_type="POINT", srid=4326),
        existing_nullable=True,
        postgresql_using="geometry::geometry(POINT,4326)",
    )
