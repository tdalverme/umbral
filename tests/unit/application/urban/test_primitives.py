"""Persisted primitive rows keep only metrics declared by the Urban contract."""

from __future__ import annotations

from uuid import uuid4

from umbral.application.urban.primitives import buckets_to_primitives
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published


def test_unsupported_primitive_counts_are_not_measured_as_zero() -> None:
    contract = load_urban_contract_published()

    rows = buckets_to_primitives(
        listing_id=uuid4(),
        snapshot_id=uuid4(),
        buckets={"subway_line": {"nearest_m": [85.0]}},
        contract=contract,
    )

    row = next(row for row in rows if row["category"] == "subway_line")
    assert row["count_300m"] is None
    assert row["count_600m"] is None
    assert row["nearest_m"] == 85.0


def test_declared_station_count_is_computed() -> None:
    contract = load_urban_contract_published()

    rows = buckets_to_primitives(
        listing_id=uuid4(),
        snapshot_id=uuid4(),
        buckets={"subway_station": {"count_600m": [100.0, 500.0]}},
        contract=contract,
    )

    row = next(row for row in rows if row["category"] == "subway_station")
    assert row["count_300m"] is None
    assert row["count_600m"] == 2
    assert row["nearest_m"] == 100.0
