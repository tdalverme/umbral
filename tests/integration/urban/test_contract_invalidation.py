# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US3 T030: a new contract version supersedes the old and its observations.

Registering a fresh contract marks the prior contract superseded and the
previously active urban observations as invalidated, so stale signals are
never shown as current after the contract lifecycle advances.
"""

from __future__ import annotations

from uuid import uuid4

from tests.integration.urban.conftest import (
    observations_for_listing,
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_contract,
    seed_urban_snapshot,
    urban_repos,
)


def test_contract_supersede_invalidates_previous_observations(
    urban_backend,
) -> None:
    listing_id = seed_listing(urban_backend, geometry=(-34.6, -58.42))
    snapshot_id = seed_urban_snapshot(urban_backend, poi_count=1)
    seed_urban_category(
        urban_backend,
        snapshot_id,
        category="cafe",
        osm_id="c1",
        lon=-58.42,
        lat=-34.6,
    )
    seed_urban_contract(urban_backend)

    run_urban_batch(urban_backend)

    before = observations_for_listing(urban_backend, listing_id)
    assert before, "a contract should have produced urban observations"
    cafe_before = [item for item in before if item["concept_key"] == "proximidad_cafes"]
    assert cafe_before, "proximidad_cafes should have an observation"
    assert all(item["state"] == "active" for item in cafe_before)

    contracts = urban_repos(urban_backend)["contracts"]
    old_active = contracts.active()
    assert old_active is not None and old_active.status == "active"

    superseding = contracts.register(
        contract_version="urban-contract-v2",
        payload={"contract_version": "urban-contract-v2"},
        correlation_id=uuid4(),
    )
    assert superseding.status == "active"

    after = observations_for_listing(urban_backend, listing_id)
    cafe_after = [item for item in after if item["concept_key"] == "proximidad_cafes"]
    assert cafe_after, "proximidad_cafes should still have an observation"
    assert all(item["state"] == "invalidated" for item in cafe_after)
