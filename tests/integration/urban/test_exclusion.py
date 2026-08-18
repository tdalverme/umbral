# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US1 T015: a listing without precise coordinates is excluded and unknown."""

from __future__ import annotations

from tests.integration.urban.conftest import (
    run_urban_batch,
    seed_listing,
    seed_urban_snapshot,
)


def test_listing_without_precise_coordinates_gets_no_urban_signals(
    urban_backend,
) -> None:
    seed_listing(
        urban_backend,
        geometry=None,
        geo_precision="neighborhood",
        neighborhood="Caballito",
    )
    seed_urban_snapshot(urban_backend)

    outcome = run_urban_batch(urban_backend)

    assert outcome.listings_processed == 0
    assert outcome.signal_rows == 0
    assert outcome.stats_rows == 0
    assert outcome.observation_count == 0
