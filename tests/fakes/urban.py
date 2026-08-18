"""In-memory adapters for the urban application ports used in unit tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from uuid import UUID, uuid4


class FakeUrbanContractRepository:
    def __init__(self) -> None:
        self._active: object | None = None

    def set_active(self, contract_version_id: UUID) -> None:
        self._active = _ContractLike(contract_version_id)

    def active(self) -> object | None:
        return self._active

    def register(self, **kwargs: object) -> object:
        return _ContractLike(uuid4())


class _ContractLike:
    def __init__(self, version_id: UUID) -> None:
        self.id = version_id


class FakeUrbanSnapshotRepository:
    def __init__(self) -> None:
        self._active: object | None = None

    def set_active(self, snapshot_id: UUID) -> None:
        self._active = _SnapshotLike(snapshot_id)

    def active(self) -> object | None:
        return self._active

    def create(self, **kwargs: object) -> object:
        return _SnapshotLike(uuid4())

    def mark_ready(self, snapshot_id: UUID, **kwargs: object) -> object:
        return _SnapshotLike(snapshot_id)


class _SnapshotLike:
    def __init__(self, snapshot_id: UUID) -> None:
        self.id = snapshot_id


class FakeDistanceCalculator:
    def __init__(self) -> None:
        self.buckets: Mapping[str, Mapping[str, list[float]]] = {}
        self.calls: list[tuple[UUID, UUID]] = []

    def set_buckets(
        self, buckets: Mapping[str, Mapping[str, list[float]]]
    ) -> None:
        self.buckets = buckets

    def for_listing(
        self,
        listing_id: UUID,
        snapshot_id: UUID,
        *,
        radius_m: int,
    ) -> Mapping[str, Mapping[str, list[float]]]:
        self.calls.append((listing_id, snapshot_id))
        return self.buckets


class FakeListingsCoordinatesReader:
    def __init__(self) -> None:
        self.listings: dict[UUID, str] = {}

    def add(self, listing_id: UUID, neighborhood: str) -> None:
        self.listings[listing_id] = neighborhood

    def listing_ids_with_precise_coordinates(self) -> tuple[UUID, ...]:
        return tuple(self.listings)

    def neighborhood_of(self, listing_id: UUID) -> str | None:
        return self.listings.get(listing_id)


class FakeUrbanPrimitiveRepository:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, object]] = []

    def upsert_many(
        self, rows: Sequence[Mapping[str, object]], *, correlation_id: UUID
    ) -> None:
        self.rows.extend(rows)

    def for_listing_snapshot(
        self, listing_id: UUID, snapshot_id: UUID
    ) -> tuple[Mapping[str, object], ...]:
        return tuple(
            row for row in self.rows if row["listing_id"] == listing_id
        )

    def listing_ids_with_precise_coordinates(self) -> tuple[UUID, ...]:
        return ()

    def listing_ids_with_coordinates(self) -> tuple[UUID, ...]:
        return ()


class FakeUrbanSignalRepository:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, object]] = []

    def replace_for_contract(
        self, contract_version_id: UUID, rows: Sequence[Mapping[str, object]]
    ) -> None:
        self.rows = list(rows)

    def for_listing_contract(
        self, listing_id: UUID, contract_version_id: UUID
    ) -> tuple[Mapping[str, object], ...]:
        return tuple(
            row
            for row in self.rows
            if row["listing_id"] == listing_id
        )

    def upsert(self, signal: Mapping[str, object], *, correlation_id: UUID) -> None:
        self.rows.append(signal)


class FakeNeighborhoodStatsRepository:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, object]] = []

    def replace_for_snapshot(
        self, snapshot_id: UUID, rows: Sequence[Mapping[str, object]]
    ) -> None:
        self.rows = list(rows)

    def for_barrio_signal(
        self, barrio: str, signal: str, snapshot_id: UUID
    ) -> Mapping[str, object] | None:
        return next(
            (
                row
                for row in self.rows
                if row["barrio"] == barrio and row["signal"] == signal
            ),
            None,
        )


def utcnow() -> datetime:
    return datetime(2026, 8, 1, tzinfo=timezone.utc)
