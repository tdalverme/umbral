"""SQLAlchemy adapters for the urban signal domain."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from umbral.infrastructure.db.models.silver import SilverListing
from umbral.infrastructure.db.models.urban import (
    NeighborhoodSignalStats as NeighborhoodSignalStatsModel,
)
from umbral.infrastructure.db.models.urban import UrbanContract as UrbanContractModel
from umbral.infrastructure.db.models.urban import (
    UrbanPrimitive as UrbanPrimitiveModel,
)
from umbral.infrastructure.db.models.urban import UrbanSignal as UrbanSignalModel
from umbral.infrastructure.db.models.urban import UrbanSnapshot as UrbanSnapshotModel
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyObservationRepository,
)

SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyUrbanContractRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def active(self) -> UrbanContractModel | None:
        with self.session_factory() as session:
            return session.scalar(
                select(UrbanContractModel).where(
                    UrbanContractModel.status == "active"
                )
            )

    def register(
        self,
        *,
        contract_version: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> UrbanContractModel:
        with self.session_factory() as session:
            existing = session.scalar(
                select(UrbanContractModel).where(
                    UrbanContractModel.status == "active"
                )
            )
            if existing is not None:
                existing.status = "superseded"
                existing.updated_at = now or _now()
                SqlAlchemyObservationRepository(
                    self.session_factory
                ).invalidate_active_for_source("urban")
            stamp = now or _now()
            model = UrbanContractModel(
                id=uuid4(),
                created_at=stamp,
                updated_at=stamp,
                actor_kind="service",
                actor_id=None,
                source="urban.contract",
                correlation_id=correlation_id,
                contract_version=contract_version,
                payload=dict(payload),
                status="active",
                superseded_by=None,
            )
            session.add(model)
            session.commit()
            return model


class SqlAlchemyUrbanSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def create(
        self,
        *,
        source_path: str,
        source_hash: str | None,
        data_date: datetime | None,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> UrbanSnapshotModel:
        stamp = now or _now()
        with self.session_factory() as session:
            model = UrbanSnapshotModel(
                id=uuid4(),
                created_at=stamp,
                updated_at=stamp,
                actor_kind="service",
                actor_id=None,
                source="urban.snapshot",
                correlation_id=correlation_id,
                source_path=source_path,
                source_hash=source_hash,
                data_date=data_date,
                status="importing",
                poi_count=0,
                linear_count=0,
            )
            session.add(model)
            session.commit()
            return model

    def mark_ready(
        self,
        snapshot_id: UUID,
        *,
        poi_count: int,
        linear_count: int,
        correlation_id: UUID,
    ) -> UrbanSnapshotModel:
        with self.session_factory() as session:
            model = session.get(UrbanSnapshotModel, snapshot_id)
            if model is None:
                raise KeyError(snapshot_id)
            model.status = "ready"
            model.poi_count = poi_count
            model.linear_count = linear_count
            model.correlation_id = correlation_id
            model.updated_at = _now()
            session.commit()
            return model

    def active(self) -> UrbanSnapshotModel | None:
        with self.session_factory() as session:
            return session.scalar(
                select(UrbanSnapshotModel)
                .where(UrbanSnapshotModel.status == "ready")
                .order_by(UrbanSnapshotModel.created_at.desc())
                .limit(1)
            )


class SqlAlchemyUrbanPrimitiveRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def upsert_many(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        correlation_id: UUID,
    ) -> None:
        if not rows:
            return
        stamp = _now()
        with self.session_factory() as session:
            for row in rows:
                listing_id = cast(UUID, row["listing_id"])
                snapshot_id = cast(UUID, row["snapshot_id"])
                category = str(row["category"])
                existing = session.scalar(
                    select(UrbanPrimitiveModel).where(
                        UrbanPrimitiveModel.listing_id == listing_id,
                        UrbanPrimitiveModel.snapshot_id == snapshot_id,
                        UrbanPrimitiveModel.category == category,
                    )
                )
                if existing is not None:
                    existing.count_300m = _int(row.get("count_300m"), 0)
                    existing.count_600m = _int(row.get("count_600m"), 0)
                    existing.nearest_m = _opt_float(row.get("nearest_m"))
                    existing.updated_at = stamp
                    existing.correlation_id = correlation_id
                else:
                    session.add(
                        UrbanPrimitiveModel(
                            id=uuid4(),
                            created_at=stamp,
                            updated_at=stamp,
                            actor_kind="service",
                            actor_id=None,
                            source="urban.primitive",
                            correlation_id=correlation_id,
                            listing_id=listing_id,
                            snapshot_id=snapshot_id,
                            category=category,
                            kind=str(row.get("kind", "poi")),
                            count_300m=_int(row.get("count_300m"), 0),
                            count_600m=_int(row.get("count_600m"), 0),
                            nearest_m=_opt_float(row.get("nearest_m")),
                        )
                    )
            session.commit()

    def for_listing_snapshot(
        self, listing_id: UUID, snapshot_id: UUID
    ) -> tuple[Mapping[str, object], ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(UrbanPrimitiveModel).where(
                    UrbanPrimitiveModel.listing_id == listing_id,
                    UrbanPrimitiveModel.snapshot_id == snapshot_id,
                )
            )
            return tuple(
                {
                    "category": item.category,
                    "kind": item.kind,
                    "count_300m": item.count_300m,
                    "count_600m": item.count_600m,
                    "nearest_m": item.nearest_m,
                }
                for item in models
            )

    def listing_ids_with_precise_coordinates(self) -> tuple[UUID, ...]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(SilverListing.id).where(
                    SilverListing.geo_precision.in_(["exact", "block"])
                )
            )
            return tuple(rows)

    def listing_ids_with_coordinates(self) -> tuple[UUID, ...]:
        return self.listing_ids_with_precise_coordinates()


class SqlAlchemyUrbanListingReader:
    """Reads precise-coordinate listings and their normalized barrio."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def listing_ids_with_precise_coordinates(self) -> tuple[UUID, ...]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(SilverListing.id).where(
                    SilverListing.geo_precision.in_(["exact", "block"])
                )
            )
            return tuple(rows)

    def neighborhood_of(self, listing_id: UUID) -> str | None:
        with self.session_factory() as session:
            return session.scalar(
                select(SilverListing.neighborhood).where(
                    SilverListing.id == listing_id
                )
            )


class SqlAlchemyUrbanSignalRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def replace_for_contract(
        self,
        contract_version_id: UUID,
        rows: Sequence[Mapping[str, object]],
    ) -> None:
        stamp = _now()
        with self.session_factory() as session:
            session.execute(
                delete(UrbanSignalModel).where(
                    UrbanSignalModel.contract_version_id == contract_version_id
                )
            )
            for row in rows:
                session.add(
                    UrbanSignalModel(
                        id=uuid4(),
                        created_at=stamp,
                        updated_at=stamp,
                        actor_kind="service",
                        actor_id=None,
                        source="urban.signal",
                        correlation_id=cast(UUID, row.get("correlation_id", uuid4())),
                        listing_id=cast(UUID, row["listing_id"]),
                        snapshot_id=cast(UUID, row["snapshot_id"]),
                        contract_version_id=contract_version_id,
                        signal=str(row["signal"]),
                        value=_float(row["value"]),
                        normalized_value=_opt_float(row.get("normalized_value")),
                        normalization_scope=str(
                            row.get("normalization_scope", "barrio")
                        ),
                        confidence=_float(row["confidence"]),
                        missing=bool(row.get("missing", False)),
                        contributors=_contributors(row.get("contributors")),
                    )
                )
            session.commit()

    def for_listing_contract(
        self, listing_id: UUID, contract_version_id: UUID
    ) -> tuple[Mapping[str, object], ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(UrbanSignalModel).where(
                    UrbanSignalModel.listing_id == listing_id,
                    UrbanSignalModel.contract_version_id == contract_version_id,
                )
            )
            return tuple(
                {
                    "signal": item.signal,
                    "value": item.value,
                    "normalized_value": item.normalized_value,
                    "normalization_scope": item.normalization_scope,
                    "confidence": item.confidence,
                    "missing": item.missing,
                    "contributors": list(item.contributors or []),
                }
                for item in models
            )


class SqlAlchemyNeighborhoodStatsRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def replace_for_snapshot(
        self,
        snapshot_id: UUID,
        rows: Sequence[Mapping[str, object]],
    ) -> None:
        stamp = _now()
        with self.session_factory() as session:
            session.execute(
                delete(NeighborhoodSignalStatsModel).where(
                    NeighborhoodSignalStatsModel.snapshot_id == snapshot_id
                )
            )
            for row in rows:
                session.add(
                    NeighborhoodSignalStatsModel(
                        id=uuid4(),
                        created_at=stamp,
                        updated_at=stamp,
                        actor_kind="service",
                        actor_id=None,
                        source="urban.stats",
                        correlation_id=cast(UUID, row.get("correlation_id", uuid4())),
                        snapshot_id=snapshot_id,
                        barrio=str(row["barrio"]),
                        signal=str(row["signal"]),
                        sample_size=_int(row["sample_size"], 0),
                        normalization_scope=str(row["normalization_scope"]),
                        p50=_opt_float(row.get("p50")),
                        p75=_opt_float(row.get("p75")),
                        p90=_opt_float(row.get("p90")),
                    )
                )
            session.commit()

    def for_barrio_signal(
        self, barrio: str, signal: str, snapshot_id: UUID
    ) -> Mapping[str, object] | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(NeighborhoodSignalStatsModel).where(
                    NeighborhoodSignalStatsModel.barrio == barrio,
                    NeighborhoodSignalStatsModel.signal == signal,
                    NeighborhoodSignalStatsModel.snapshot_id == snapshot_id,
                )
            )
            if model is None:
                return None
            return {
                "barrio": model.barrio,
                "signal": model.signal,
                "sample_size": model.sample_size,
                "normalization_scope": model.normalization_scope,
                "p50": model.p50,
                "p75": model.p75,
                "p90": model.p90,
            }


def _int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def _float(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _contributors(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            out.append(dict(item))
    return out
