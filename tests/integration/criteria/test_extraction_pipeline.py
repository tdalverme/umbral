"""Integration: rule extraction pipeline over real Postgres."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from tests.integration.criteria.conftest import (
    build_criteria_service,
    seed_silver_listings,
)

from umbral.application.criteria.contracts import RecomputeScope
from umbral.infrastructure.db.models.criteria import (
    ListingObservation as ObservationModel,
)


def test_rule_pipeline_persists_observations_with_evidence(
    criteria_backend: Any,
) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=3)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    summary = service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    assert summary["published"] == 3
    with factory() as session:
        rows = session.execute(
            select(ObservationModel).where(ObservationModel.concept_key == "balcon")
        )
        observations = list(rows.scalars())
    assert len(observations) == 3
    assert all(observation.state == "active" for observation in observations)
    assert all(observation.source == "rule" for observation in observations)
    assert all(
        observation.evidence.get("fragment") is not None or observation.value is None
        for observation in observations
    )
    assert all(
        observation.extraction_version_id is not None for observation in observations
    )


def test_replay_does_not_duplicate_active_observations(criteria_backend: Any) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=1)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    scope = RecomputeScope("concept", "balcon")
    service.process_extraction(scope, job_execution_id=uuid4())
    service.process_extraction(scope, job_execution_id=uuid4())
    with factory() as session:
        rows = session.execute(
            select(ObservationModel).where(
                ObservationModel.concept_key == "balcon",
                ObservationModel.state == "active",
            )
        )
        assert len(list(rows.scalars())) == 1
