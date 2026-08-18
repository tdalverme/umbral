# mypy: disable-error-code="no-untyped-def,attr-defined,arg-type"
"""US4 T036: every urban observation traces to its contract and snapshot.

The observation evidence cites the contract version and the snapshot; the
snapshot itself exposes source path, hash and data date so an observation can
be reconstructed and licensed.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from tests.integration.urban.conftest import (
    observations_for_listing,
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_contract,
    seed_urban_snapshot,
)

from umbral.infrastructure.db.models.urban import UrbanSnapshot

_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
_HASH = "ab" * 32


def test_observation_traces_to_contract_and_snapshot(urban_backend) -> None:
    listing_id = seed_listing(urban_backend, geometry=(-34.6, -58.42))
    snapshot_id = seed_urban_snapshot(
        urban_backend,
        source_path="objects/urban/argentina-2026-08.osm.pbf",
        source_hash=_HASH,
        poi_count=1,
    )
    seed_urban_category(
        urban_backend,
        snapshot_id,
        category="cafe",
        osm_id="c1",
        lon=-58.42,
        lat=-34.6,
    )
    contract_id, contract_version = seed_urban_contract(urban_backend)

    run_urban_batch(urban_backend)

    observations = observations_for_listing(urban_backend, listing_id)
    assert observations
    evidence = cast(Mapping[str, object], observations[0]["evidence"])
    assert evidence["contract_version_id"] == str(contract_id)
    assert evidence["snapshot_id"] == str(snapshot_id)

    with urban_backend() as session:
        snapshot = session.scalar(
            select(UrbanSnapshot).where(UrbanSnapshot.id == snapshot_id)
        )
        assert snapshot is not None
        assert snapshot.source_path == "objects/urban/argentina-2026-08.osm.pbf"
        assert snapshot.source_hash == _HASH
        assert snapshot.data_date == _NOW

    assert contract_version == "urban-contract-v1"
