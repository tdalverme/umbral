"""Atomic, idempotent replacement of one stored Urban snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select

from tests.integration.urban.conftest import (
    seed_listing,
    seed_urban_category,
    seed_urban_contract,
    seed_urban_snapshot,
    urban_repos,
)
from umbral.infrastructure.db.models.urban import (
    NeighborhoodSignalStats,
    UrbanCategory,
    UrbanPrimitive,
    UrbanSignal,
)


def _staged_category(snapshot_id, osm_id: str) -> UrbanCategory:
    now = datetime.now(timezone.utc)
    return UrbanCategory(
        id=uuid4(),
        created_at=now,
        updated_at=now,
        actor_kind="service",
        actor_id=None,
        source="urban.osm",
        correlation_id=uuid4(),
        snapshot_id=snapshot_id,
        osm_id=osm_id,
        category="subway_line",
        kind="linear",
        name="Line D",
        tags={"ref": "D"},
        geometry=WKTElement(
            "SRID=4326;LINESTRING(-58.42 -34.6,-58.40 -34.6)"
        ),
    )


def test_rebuild_replaces_snapshot_derived_rows_atomically_and_idempotently(
    urban_backend,
) -> None:
    listing_id = seed_listing(urban_backend)
    snapshot_id = seed_urban_snapshot(
        urban_backend,
        source_path="objects/urban/current.pbf",
        source_hash="a" * 64,
        poi_count=1,
        linear_count=0,
    )
    contract_id, _ = seed_urban_contract(urban_backend)
    seed_urban_category(
        urban_backend,
        snapshot_id,
        category="cafe",
        osm_id="old-poi",
    )
    repos = urban_repos(urban_backend)
    repos["primitives"].upsert_many(
        (
            {
                "listing_id": listing_id,
                "snapshot_id": snapshot_id,
                "category": "cafe",
                "kind": "poi",
                "count_300m": 1,
                "count_600m": 2,
                "nearest_m": 100.0,
            },
        ),
        correlation_id=uuid4(),
    )
    repos["signals"].replace_for_snapshot_contract(
        snapshot_id,
        contract_id,
        [
            {
                "listing_id": listing_id,
                "snapshot_id": snapshot_id,
                "signal": "cafe_lifestyle",
                "value": 0.4,
                "normalized_value": 0.4,
                "normalization_scope": "barrio",
                "confidence": 0.8,
                "missing": False,
                "contributors": [],
            }
        ],
    )
    repos["stats"].replace_for_snapshot(
        snapshot_id,
        [
            {
                "barrio": "Caballito",
                "signal": "cafe_lifestyle",
                "sample_size": 1,
                "normalization_scope": "barrio",
                "p50": 0.4,
                "p75": 0.4,
                "p90": 0.4,
            }
        ],
    )

    snapshots = repos["snapshots"]
    snapshots.replace_snapshot_derived(
        snapshot_id,
        [_staged_category(snapshot_id, "new-line")],
        poi_count=0,
        linear_count=1,
        correlation_id=uuid4(),
    )

    with urban_backend() as session:
        assert session.scalar(
            select(func.count()).select_from(UrbanCategory).where(
                UrbanCategory.snapshot_id == snapshot_id
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(UrbanCategory).where(
                UrbanCategory.osm_id == "old-poi"
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(UrbanPrimitive).where(
                UrbanPrimitive.snapshot_id == snapshot_id
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(UrbanSignal).where(
                UrbanSignal.snapshot_id == snapshot_id
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(NeighborhoodSignalStats).where(
                NeighborhoodSignalStats.snapshot_id == snapshot_id
            )
        ) == 0

    snapshots.replace_snapshot_derived(
        snapshot_id,
        [_staged_category(snapshot_id, "new-line")],
        poi_count=0,
        linear_count=1,
        correlation_id=uuid4(),
    )

    with urban_backend() as session:
        assert session.scalar(
            select(func.count()).select_from(UrbanCategory).where(
                UrbanCategory.snapshot_id == snapshot_id
            )
        ) == 1
