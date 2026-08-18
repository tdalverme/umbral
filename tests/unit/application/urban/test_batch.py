"""US1: the batch orchestrator turns distances into signals and observations."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.fakes.urban import (
    FakeDistanceCalculator,
    FakeListingsCoordinatesReader,
    FakeNeighborhoodStatsRepository,
    FakeUrbanContractRepository,
    FakeUrbanPrimitiveRepository,
    FakeUrbanSignalRepository,
    FakeUrbanSnapshotRepository,
    utcnow,
)

from umbral.application.urban.batch import UrbanBatchService
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published

_CONCEPTS = {
    "proximidad_cafes": "cafe_lifestyle",
    "acceso_transporte": "transit_access",
}

_Service = tuple[
    UrbanBatchService,
    FakeDistanceCalculator,
    FakeUrbanSignalRepository,
    FakeListingsCoordinatesReader,
]


@pytest.fixture
def service() -> _Service:
    contract = load_urban_contract_published()
    contract_repo = FakeUrbanContractRepository()
    contract_repo.set_active(uuid4())
    snapshot_repo = FakeUrbanSnapshotRepository()
    snapshot_repo.set_active(uuid4())
    distances = FakeDistanceCalculator()
    listings = FakeListingsCoordinatesReader()
    signals = FakeUrbanSignalRepository()
    service = UrbanBatchService(
        contract=contract,
        distances=distances,
        primitives=FakeUrbanPrimitiveRepository(),
        signals=signals,
        stats=FakeNeighborhoodStatsRepository(),
        contracts=contract_repo,
        snapshots=snapshot_repo,
        listings=listings,
        extraction_version_id=uuid4(),
        concepts=_CONCEPTS,
        created_at=utcnow(),
    )
    return service, distances, signals, listings


def test_batch_produces_normalized_signals_and_observations(
    service: _Service,
) -> None:
    batch, distances, signals, listings = service
    listing_id = uuid4()
    distances.set_buckets(
        {
            "cafe": {
                "count_300m": [50.0, 200.0],
                "count_600m": [50.0, 200.0],
                "nearest_m": [50.0, 200.0],
            }
        }
    )
    listings.add(listing_id, "Caballito")

    outcome = batch.run(correlation_id=uuid4())

    assert outcome.listings_processed == 1
    assert outcome.signal_rows > 0
    assert outcome.stats_rows > 0
    client_rows = signals.for_listing_contract(listing_id, uuid4())
    assert any(str(row["signal"]) == "cafe_lifestyle" for row in client_rows)
    assert outcome.observation_count == 2


def test_listing_without_coordinates_is_excluded(
    service: _Service,
) -> None:
    batch, distances, _signals, _listings = service
    # No precise-coordinate listings are registered.
    distances.set_buckets({"cafe": {"nearest_m": [100.0]}})

    outcome = batch.run(correlation_id=uuid4())

    assert outcome.listings_processed == 0
    assert outcome.signal_rows == 0
    assert outcome.observation_count == 0


def test_batch_raises_without_active_contract() -> None:
    contract = load_urban_contract_published()
    contract_repo = FakeUrbanContractRepository()
    snapshot_repo = FakeUrbanSnapshotRepository()
    snapshot_repo.set_active(uuid4())
    batch = UrbanBatchService(
        contract=contract,
        distances=FakeDistanceCalculator(),
        primitives=FakeUrbanPrimitiveRepository(),
        signals=FakeUrbanSignalRepository(),
        stats=FakeNeighborhoodStatsRepository(),
        contracts=contract_repo,
        snapshots=snapshot_repo,
        listings=FakeListingsCoordinatesReader(),
        extraction_version_id=uuid4(),
        concepts=_CONCEPTS,
        created_at=utcnow(),
    )
    with pytest.raises(RuntimeError, match="urban_contract_missing"):
        batch.run(correlation_id=uuid4())
