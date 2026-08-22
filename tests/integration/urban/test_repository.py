# mypy: disable-error-code="no-untyped-def,attr-defined,operator,arg-type,index"
"""US1 T013: SQLAlchemy urban repositories conform over PostGIS."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.integration.urban.conftest import (
    seed_listing,
    seed_urban_contract,
    seed_urban_snapshot,
    urban_repos,
)

_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
_CID = uuid4()


def test_snapshot_create_mark_ready_active(urban_backend) -> None:
    snapshots = urban_repos(urban_backend)["snapshots"]
    created = snapshots.create(
        source_path="objects/urban/a.osm.pbf",
        source_hash="a" * 64,
        data_date=_NOW,
        correlation_id=_CID,
        now=_NOW,
    )
    assert created.status == "importing"
    ready = snapshots.mark_ready(
        created.id, poi_count=3, linear_count=2, correlation_id=_CID
    )
    assert ready.status == "ready"
    active = snapshots.active()
    assert active is not None and active.id == created.id


def test_contract_register_active_supersede(urban_backend) -> None:
    contracts = urban_repos(urban_backend)["contracts"]
    first = contracts.register(
        contract_version="urban-contract-v1",
        payload={"contract_version": "urban-contract-v1"},
        correlation_id=_CID,
        now=_NOW,
    )
    assert first.status == "active"
    second = contracts.register(
        contract_version="urban-contract-v2",
        payload={"contract_version": "urban-contract-v2"},
        correlation_id=_CID,
        now=_NOW,
    )
    assert second.status == "active"
    refreshed = contracts.active()
    assert refreshed is not None and refreshed.id == second.id


def test_primitives_upsert_and_for_listing_snapshot(urban_backend) -> None:
    listing_id = seed_listing(urban_backend)
    snapshot_id = seed_urban_snapshot(urban_backend)
    primitives = urban_repos(urban_backend)["primitives"]
    row = {
        "listing_id": listing_id,
        "snapshot_id": snapshot_id,
        "category": "cafe",
        "kind": "poi",
        "count_300m": 2,
        "count_600m": 3,
        "nearest_m": 120.0,
    }
    primitives.upsert_many((row,), correlation_id=_CID)
    rows = primitives.for_listing_snapshot(listing_id, snapshot_id)
    assert len(rows) == 1
    assert rows[0]["category"] == "cafe"
    assert rows[0]["count_300m"] == 2


def test_signals_replace_for_snapshot_contract(urban_backend) -> None:
    listing_id = seed_listing(urban_backend)
    snapshot_id = seed_urban_snapshot(urban_backend)
    contract_id, _ = seed_urban_contract(urban_backend)
    signals = urban_repos(urban_backend)["signals"]
    rows = [
        {
            "listing_id": listing_id,
            "snapshot_id": snapshot_id,
            "signal": "cafe_lifestyle",
            "value": 0.4,
            "normalized_value": 0.8,
            "normalization_scope": "barrio",
            "confidence": 0.9,
            "missing": False,
            "contributors": [{"term": "cafe.count_300m", "score": 1.0}],
            "correlation_id": _CID,
        }
    ]
    signals.replace_for_snapshot_contract(snapshot_id, contract_id, rows)
    fetched = signals.for_listing_snapshot_contract(
        listing_id, snapshot_id, contract_id
    )
    assert len(fetched) == 1
    assert fetched[0]["signal"] == "cafe_lifestyle"
    assert fetched[0]["normalization_scope"] == "barrio"
    # replace wipes old rows.
    signals.replace_for_snapshot_contract(snapshot_id, contract_id, ())
    assert signals.for_listing_snapshot_contract(
        listing_id, snapshot_id, contract_id
    ) == ()


def test_signals_replace_keeps_another_snapshot(urban_backend) -> None:
    listing_id = seed_listing(urban_backend)
    first_snapshot = seed_urban_snapshot(urban_backend)
    second_snapshot = seed_urban_snapshot(urban_backend)
    contract_id, _ = seed_urban_contract(urban_backend)
    signals = urban_repos(urban_backend)["signals"]
    row = {
        "listing_id": listing_id,
        "signal": "cafe_lifestyle",
        "value": 0.4,
        "normalized_value": 0.8,
        "normalization_scope": "barrio",
        "confidence": 0.9,
        "missing": False,
        "contributors": [],
        "correlation_id": _CID,
    }
    signals.replace_for_snapshot_contract(
        first_snapshot, contract_id, [{**row, "snapshot_id": first_snapshot}]
    )
    signals.replace_for_snapshot_contract(
        second_snapshot, contract_id, [{**row, "snapshot_id": second_snapshot}]
    )

    signals.replace_for_snapshot_contract(first_snapshot, contract_id, ())

    assert signals.for_listing_snapshot_contract(
        listing_id, first_snapshot, contract_id
    ) == ()
    assert signals.for_listing_snapshot_contract(
        listing_id, second_snapshot, contract_id
    )


def test_stats_replace_for_snapshot(urban_backend) -> None:
    snapshot_id = seed_urban_snapshot(urban_backend)
    stats = urban_repos(urban_backend)["stats"]
    rows = [
        {
            "barrio": "Caballito",
            "signal": "cafe_lifestyle",
            "sample_size": 12,
            "normalization_scope": "barrio",
            "p50": 0.5,
            "p75": 0.6,
            "p90": 0.8,
        }
    ]
    stats.replace_for_snapshot(snapshot_id, rows)
    row = stats.for_barrio_signal("Caballito", "cafe_lifestyle", snapshot_id)
    assert row is not None
    assert row["sample_size"] == 12
    assert row["p90"] == 0.8
    stats.replace_for_snapshot(snapshot_id, ())
    assert (
        stats.for_barrio_signal("Caballito", "cafe_lifestyle", snapshot_id) is None
    )
