"""Durable handler for the urban signals batch worker."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from umbral.application.criteria.contracts import ListingObservation
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import event_version, validate_event
from umbral.application.jobs.contracts import (
    JobContext,
    JsonScalar,
    normalize_target,
)
from umbral.application.urban.batch import UrbanBatchService
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyObservationRepository,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.db.repositories.urban import (
    SqlAlchemyUrbanSnapshotRepository,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry
from umbral.workers.registry import JobRegistry

SessionFactory = Callable[[], Session]

URBAN_BATCH_JOB_TYPE = "urban.batch"

_IMPORT_COMPLETED_EVENT = "urban.import_completed.v1"


class UrbanBatchHandler:
    job_type = URBAN_BATCH_JOB_TYPE

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        service = self._build_service(context.correlation_id)
        outcome = service.run(correlation_id=context.correlation_id)
        observations = outcome.observations
        observations_repo = SqlAlchemyObservationRepository(self.session_factory)
        if observations:
            # Recompute replaces all urban observations: invalidate the
            # previous active ones so the unique partial index does not clash.
            observations_repo.invalidate_active_for_source("urban")
            observations_repo.publish(
                cast(tuple[ListingObservation, ...], observations),
                supersede_ids=(),
                run=None,
                event=None,
            )
        self._emit_import_completed(
            correlation_id=context.correlation_id,
            listings_processed=outcome.listings_processed,
            published_count=outcome.observation_count,
        )
        return {
            "listings_processed": outcome.listings_processed,
            "primitive_rows": outcome.primitive_rows,
            "signal_rows": outcome.signal_rows,
            "stats_rows": outcome.stats_rows,
            "observations": outcome.observation_count,
        }

    def _emit_import_completed(
        self,
        *,
        correlation_id: UUID,
        listings_processed: int,
        published_count: int,
    ) -> None:
        snapshot = SqlAlchemyUrbanSnapshotRepository(
            self.session_factory
        ).active()
        if snapshot is None:
            return
        registry = load_events_registry()
        payload: Mapping[str, object] = {
            "snapshot_id": str(snapshot.id),
            "listings_processed": listings_processed,
            "published_count": published_count,
        }
        error = validate_event(registry, _IMPORT_COMPLETED_EVENT, payload)
        if error is not None:
            raise RuntimeError(f"urban event invalid: {error}")
        version = event_version(registry, _IMPORT_COMPLETED_EVENT)
        event = ProductEvent(
            event_id=uuid4(),
            event_type=_IMPORT_COMPLETED_EVENT,
            event_version=cast(int, version),
            actor_id=None,
            occurred_at=datetime.now(timezone.utc),
            correlation_id=correlation_id,
            payload=payload,
        )
        SqlAlchemyEventRepository(self.session_factory).insert(event)

    def _build_service(self, correlation_id: UUID) -> UrbanBatchService:
        from umbral.infrastructure.urban.composition import build_urban_batch_service

        return build_urban_batch_service(
            session_factory=self.session_factory,
            correlation_id=correlation_id,
        )


def build_urban_registry(session_factory: SessionFactory) -> JobRegistry:
    handler = UrbanBatchHandler(session_factory)
    return JobRegistry({handler.job_type: handler})
