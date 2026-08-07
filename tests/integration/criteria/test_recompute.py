"""Integration: selective recompute over real Postgres with atomic publication."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from tests.integration.criteria.conftest import (
    build_criteria_service,
    seed_silver_listings,
)

from umbral.application.criteria.contracts import RecomputeScope
from umbral.infrastructure.db.models.criteria import (
    ListingObservation as ObservationModel,
)


def _states(factory: Any, concept_key: str = "balcon") -> list[tuple[object, object]]:
    with factory() as session:
        rows = session.execute(
            select(ObservationModel.state, ObservationModel.value).where(
                ObservationModel.concept_key == concept_key
            )
        )
        return [(row[0], row[1]) for row in rows]


def test_recompute_publishes_atomically_and_preserves_versions(
    criteria_backend: Any,
) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=3)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())

    first = service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    assert first["published"] == 3
    assert service.invalidate_scope(RecomputeScope("concept", "balcon")) == 3

    summary = service.process_recompute(
        RecomputeScope("concept", "balcon"),
        cause="concept:balcon",
        job_execution_id=uuid4(),
    )
    assert summary["state"] == "succeeded"
    assert summary["superseded"] == 3
    assert summary["published"] == 3

    states = _states(factory)
    assert sum(1 for state, _ in states if state == "active") == 3
    assert sum(1 for state, _ in states if state == "superseded") == 3


def test_partial_unique_index_enforces_one_active_observation(
    criteria_backend: Any,
) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=1)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    summary = service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    assert summary["published"] == 1
    states = _states(factory)
    assert sum(1 for state, _ in states if state == "active") == 1


def test_recompute_run_row_records_state_counts_and_cause(
    criteria_backend: Any,
) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=2)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    service.invalidate_scope(RecomputeScope("concept", "balcon"))
    summary = service.process_recompute(
        RecomputeScope("concept", "balcon"),
        cause="new rule v2",
        job_execution_id=uuid4(),
    )
    run_id = summary["recompute_run_id"]
    assert isinstance(run_id, str)
    run = service.recomputes.get(UUID(run_id))
    assert run is not None
    assert run.state == "succeeded"
    assert run.cause == "new rule v2"
    assert run.counts["invalidated"] == 2
    assert run.finished_at is not None
