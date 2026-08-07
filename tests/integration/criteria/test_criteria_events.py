"""Integration: criteria.* events written in the same transaction as the change."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from tests.integration.criteria.conftest import (
    build_criteria_service,
    seed_silver_listings,
)

from umbral.application.criteria.contracts import RecomputeScope
from umbral.infrastructure.db.models.radar import ProductEventRow


def _event_types(factory: Any) -> list[str]:
    with factory() as session:
        rows = session.execute(select(ProductEventRow.event_type))
        return [row[0] for row in rows]


def test_concept_version_event_is_written(criteria_backend: Any) -> None:
    factory = criteria_backend
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    service.register_concept_version(
        key="balcon",
        name="Balcon v2",
        aliases=("balcon",),
        matcher_type="categorical",
        params_schema={"allowed_values": ["true", "false"]},
        defaults={"value": "false"},
        compute_policy={"unknown": "penalize", "qualitative": False},
        correlation_id=uuid4(),
    )
    types = _event_types(factory)
    assert types.count("criteria.concept_version_created.v1") == 7  # seed + edit


def test_batch_and_recompute_events_carry_counts_only(criteria_backend: Any) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=2)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    service.invalidate_scope(RecomputeScope("concept", "balcon"))
    service.process_recompute(
        RecomputeScope("concept", "balcon"),
        cause="concept:balcon",
        job_execution_id=uuid4(),
    )
    types = _event_types(factory)
    assert types.count("criteria.observation_batch_published.v1") == 1
    assert types.count("criteria.recompute_completed.v1") == 1
    with factory() as session:
        row = session.scalar(
            select(ProductEventRow).where(
                ProductEventRow.event_type == "criteria.recompute_completed.v1"
            )
        )
        assert row is not None
        assert set(row.payload) == {
            "recompute_run_id",
            "scope_kind",
            "scope_key",
            "cause",
            "state",
            "published_count",
            "failed_count",
        }
        assert "fragment" not in row.payload
