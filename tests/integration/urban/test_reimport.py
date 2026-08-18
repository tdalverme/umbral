# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US3 T031: reimporting a new snapshot fully recalcs coordinate listings.

After a fresh snapshot (new hash/date) is imported and the batch reruns, every
listing with precise coordinates is recomputed against the new snapshot and no
signal row keeps the previous snapshot's lineage.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from tests.integration.urban.conftest import (
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_contract,
    seed_urban_snapshot,
)
from umbral.infrastructure.db.models.urban import UrbanSignal


def _signal_snapshots(factory) -> dict[UUID, set[UUID]]:
    with factory() as session:
        rows = session.execute(select(UrbanSignal.listing_id, UrbanSignal.snapshot_id))
        by_listing: dict[UUID, set[UUID]] = {}
        for listing_id, snapshot_id in rows:
            by_listing.setdefault(listing_id, set()).add(snapshot_id)
        return by_listing


def test_reimport_recalcs_all_coordinate_listings(urban_backend) -> None:
    first = seed_listing(urban_backend, geometry=(-34.6, -58.42))
    second = seed_listing(urban_backend, geometry=(-34.605, -58.43))
    seed_urban_contract(urban_backend)
    old_snapshot = seed_urban_snapshot(
        urban_backend,
        source_hash="a" * 64,
        source_path="objects/urban/argentina-2026-07.osm.pbf",
        poi_count=1,
    )
    seed_urban_category(
        urban_backend,
        old_snapshot,
        category="cafe",
        osm_id="c-old",
        lon=-58.42,
        lat=-34.6,
    )

    run_urban_batch(urban_backend)
    before = _signal_snapshots(urban_backend)
    assert set(before) == {first, second}
    assert all(snapshots == {old_snapshot} for snapshots in before.values())

    new_snapshot = seed_urban_snapshot(
        urban_backend,
        source_hash="b" * 64,
        source_path="objects/urban/argentina-2026-08.osm.pbf",
        poi_count=1,
    )
    seed_urban_category(
        urban_backend,
        new_snapshot,
        category="cafe",
        osm_id="c-new",
        lon=-58.42,
        lat=-34.6,
    )
    run_urban_batch(urban_backend, correlation_id=uuid4())

    after = _signal_snapshots(urban_backend)
    assert set(after) == {first, second}
    assert all(snapshots == {new_snapshot} for snapshots in after.values())
    assert old_snapshot not in {s for snapshots in after.values() for s in snapshots}
