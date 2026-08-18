# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US2 T024: neighborhood signal stats are replaced per job and scope is stable."""

from __future__ import annotations

from tests.integration.urban.conftest import (
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_snapshot,
    urban_repos,
)


def test_stats_replaced_in_job_and_scope_stable(urban_backend) -> None:
    for index in range(3):
        seed_listing(
            urban_backend,
            geometry=(-34.6 - index * 0.0001, -58.42),
            neighborhood="Caballito",
        )
    snapshot_id = seed_urban_snapshot(urban_backend)
    for lon, lat in [(-58.42, -34.6), (-58.421, -34.6005), (-58.419, -34.5995)]:
        seed_urban_category(
            urban_backend,
            snapshot_id,
            category="cafe",
            osm_id=f"cafe-{lon}",
            lon=lon,
            lat=lat,
        )

    first = run_urban_batch(urban_backend)
    stats = urban_repos(urban_backend)["stats"]
    first_row = stats.for_barrio_signal("Caballito", "cafe_lifestyle", snapshot_id)
    assert first_row is not None
    first_scope = first_row["normalization_scope"]
    assert first_scope in ("barrio", "caba")

    second = run_urban_batch(urban_backend)
    second_row = stats.for_barrio_signal("Caballito", "cafe_lifestyle", snapshot_id)
    assert second_row is not None
    assert second_row["normalization_scope"] == first_scope

    assert second.stats_rows > 0
    assert first.stats_rows > 0
