# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US1 T014: observations extraction over Postgres via the real batch."""

from __future__ import annotations

from tests.integration.urban.conftest import (
    observations_for_listing,
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_snapshot,
)


def test_present_signal_produces_observation_with_evidence(urban_backend) -> None:
    listing_id = seed_listing(urban_backend, geometry=(-34.6, -58.42))
    snapshot_id = seed_urban_snapshot(urban_backend, poi_count=1)
    seed_urban_category(
        urban_backend, snapshot_id, category="cafe", osm_id="c1",
        lon=-58.42, lat=-34.6,
    )

    outcome = run_urban_batch(urban_backend)
    assert outcome.listings_processed == 1

    observations = observations_for_listing(urban_backend, listing_id)
    by_concept = {obs["concept_key"]: obs for obs in observations}
    pizza = by_concept.get("proximidad_cafes")
    assert pizza is not None
    assert pizza["state"] == "active"
    assert pizza["source"] == "urban"
    assert pizza["matcher_type"] == "signal_score"
    assert float(pizza["score"]) >= 0
    assert float(pizza["confidence"]) > 0
    assert pizza["evidence"]["signal_ref"] == "cafe_lifestyle"
    assert "contributors" in pizza["evidence"]
    assert "contract_version_id" in pizza["evidence"]
    assert "snapshot_id" in pizza["evidence"]


def test_missing_signal_keeps_observation_unknown(urban_backend) -> None:
    listing_id = seed_listing(urban_backend, geometry=(-34.6, -58.42))
    seed_urban_snapshot(urban_backend, poi_count=0)
    # Only a cafe category: transit_access has no inputs -> unknown.

    outcome = run_urban_batch(urban_backend)
    assert outcome.listings_processed == 1

    observations = observations_for_listing(urban_backend, listing_id)
    by_concept = {obs["concept_key"]: obs for obs in observations}
    transit = by_concept.get("acceso_transporte")
    assert transit is not None
    assert transit["state"] == "failed"
    assert transit["failure_code"] == "criteria.urban_unavailable"
    assert float(transit["score"]) == 0
