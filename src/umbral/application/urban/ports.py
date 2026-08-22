"""Application ports for the urban signal domain."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID


class UrbanContractRepository(Protocol):
    def active(self) -> object | None: ...

    def register(
        self,
        *,
        contract_version: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
        now: datetime,
    ) -> object: ...


class UrbanSnapshotRepository(Protocol):
    def create(
        self,
        *,
        source_path: str,
        source_hash: str | None,
        data_date: datetime | None,
        correlation_id: UUID,
        now: datetime,
    ) -> object: ...

    def mark_ready(
        self,
        snapshot_id: UUID,
        *,
        poi_count: int,
        linear_count: int,
        correlation_id: UUID,
    ) -> object: ...

    def active(self) -> object | None: ...

    def replace_snapshot_derived(
        self,
        snapshot_id: UUID,
        rows: Sequence[object],
        *,
        poi_count: int,
        linear_count: int,
        correlation_id: UUID,
    ) -> None: ...


class UrbanPrimitiveRepository(Protocol):
    def upsert_many(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        correlation_id: UUID,
    ) -> None: ...

    def for_listing_snapshot(
        self, listing_id: UUID, snapshot_id: UUID
    ) -> tuple[Mapping[str, object], ...]: ...

    def listing_ids_with_coordinates(self) -> tuple[UUID, ...]: ...


class UrbanSignalRepositoryPort(Protocol):
    def replace_for_snapshot_contract(
        self,
        snapshot_id: UUID,
        contract_version_id: UUID,
        rows: Sequence[Mapping[str, object]],
    ) -> None: ...

    def for_listing_snapshot_contract(
        self,
        listing_id: UUID,
        snapshot_id: UUID,
        contract_version_id: UUID,
    ) -> tuple[Mapping[str, object], ...]: ...


class NeighborhoodStatsRepository(Protocol):
    def replace_for_snapshot(
        self, snapshot_id: UUID, rows: Sequence[Mapping[str, object]]
    ) -> None: ...

    def for_barrio_signal(
        self, barrio: str, signal: str, snapshot_id: UUID
    ) -> Mapping[str, object] | None: ...


class ListingsCoordinatesReader(Protocol):
    def listing_ids_with_precise_coordinates(self) -> tuple[UUID, ...]: ...

    def neighborhood_of(self, listing_id: UUID) -> str | None: ...


class DistanceCalculator(Protocol):
    """Compute per-listing distance buckets from category geometry.

    Returns a mapping ``category -> metric -> [distances_m]`` for every metric
    the contract declares for that category (all metrics share the same
    distance list within the contract radius).
    """

    def for_listing(
        self,
        listing_id: UUID,
        snapshot_id: UUID,
        *,
        radius_m: int,
    ) -> Mapping[str, Mapping[str, list[float]]]: ...
