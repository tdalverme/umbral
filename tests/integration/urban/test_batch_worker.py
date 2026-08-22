# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US1 T016: the batch worker produces primitives, signals, stats, observations."""

from __future__ import annotations

from tests.integration.urban.conftest import (
    observations_for_listing,
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_snapshot,
    urban_repos,
)


def test_batch_worker_produces_all_artifacts(urban_backend) -> None:
    listing_id = seed_listing(urban_backend, geometry=(-34.6, -58.42))
    snapshot_id = seed_urban_snapshot(urban_backend)
    for osm_id, category, lon, lat in [
        ("c1", "cafe", -58.42, -34.6),
        ("c2", "supermarket", -58.421, -34.6),
        ("b1", "bus_stop", -58.419, -34.601),
        ("p1", "pharmacy", -58.42, -34.598),
    ]:
        seed_urban_category(
            urban_backend,
            snapshot_id,
            category=category,
            osm_id=osm_id,
            lon=lon,
            lat=lat,
        )

    outcome = run_urban_batch(urban_backend)

    assert outcome.listings_processed == 1
    assert outcome.primitive_rows > 0
    assert outcome.signal_rows > 0
    assert outcome.stats_rows > 0
    assert outcome.observation_count > 0

    repos = urban_repos(urban_backend)
    contract_id = repos["contracts"].active().id
    signals = repos["signals"].for_listing_snapshot_contract(
        listing_id, snapshot_id, contract_id
    )
    names = {str(row["signal"]) for row in signals}
    assert "cafe_lifestyle" in names
    primitives = repos["primitives"].for_listing_snapshot(listing_id, snapshot_id)
    categories = {str(row["category"]) for row in primitives}
    assert "cafe" in categories

    observations = observations_for_listing(urban_backend, listing_id)
    assert any(obs["concept_key"] == "proximidad_cafes" for obs in observations)
