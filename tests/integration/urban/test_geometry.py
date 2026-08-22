"""PostGIS distances use the nearest point on imported linear geometry."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from geoalchemy2.elements import WKTElement

from tests.integration.urban.conftest import (
    seed_listing,
    seed_urban_snapshot,
)
from umbral.infrastructure.db.models.urban import UrbanCategory
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published
from umbral.infrastructure.urban.distance_calculator import SqlAlchemyDistanceCalculator


def test_distance_to_linear_feature_uses_all_way_nodes(urban_backend) -> None:
    listing_id = seed_listing(urban_backend, geometry=(-34.6, -58.41))
    snapshot_id = seed_urban_snapshot(urban_backend, linear_count=1)
    with urban_backend() as session:
        now = datetime.now(timezone.utc)
        session.add(
            UrbanCategory(
                id=uuid4(),
                created_at=now,
                updated_at=now,
                actor_kind="service",
                actor_id=None,
                source="urban.test",
                correlation_id=uuid4(),
                snapshot_id=snapshot_id,
                osm_id="w-middle",
                category="subway_line",
                kind="linear",
                name="Line D",
                tags={"ref": "D"},
                geometry=WKTElement(
                    "SRID=4326;LINESTRING(-58.42 -34.6,-58.40 -34.6)"
                ),
            )
        )
        session.commit()

    calculator = SqlAlchemyDistanceCalculator(
        urban_backend, load_urban_contract_published()
    )
    buckets = calculator.for_listing(
        listing_id,
        snapshot_id,
        radius_m=1200,
    )

    assert buckets["subway_line"]["nearest_m"][0] < 1.0
