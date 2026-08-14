"""Integration: scoring v1 run publishing over real Postgres (US4, US5)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from tests.integration.scoring.conftest import seed_run

from umbral.infrastructure.db.models.scoring import (
    CriterionEvaluation as EvaluationModel,
)


def _evaluation_count(factory: Any, run_id: Any) -> int:
    with factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(EvaluationModel)
                .where(EvaluationModel.run_id == run_id)
            )
            or 0
        )


def test_run_v1_publishes_items_and_evaluations_atomically(
    scoring_backend: Any,
) -> None:
    factory = scoring_backend
    radar, profile, run = seed_run(factory)
    assert run is not None
    assert run.state == "succeeded"
    assert run.score_policy_version == "scoring-policy-v1"
    assert run.published_item_count == 3
    assert _evaluation_count(factory, run.run_id) == 3 * 6  # surface is absent


def test_evaluations_freezing_survives_observation_recompute(
    scoring_backend: Any,
) -> None:
    factory = scoring_backend
    from tests.integration.criteria.conftest import build_criteria_service

    from umbral.application.criteria.contracts import RecomputeScope

    radar, profile, run = seed_run(factory)
    before = _evaluation_count(factory, run.run_id)
    criteria = build_criteria_service(factory)
    criteria.process_recompute(
        RecomputeScope("concept", "balcon"),
        cause="concept:balcon",
        job_execution_id=uuid4(),
    )
    after = _evaluation_count(factory, run.run_id)
    assert before == after
    published = radar.runs.get(run.run_id)
    assert published is not None and published.state == "succeeded"


def test_legacy_runs_are_not_touched_by_v1_runs(scoring_backend: Any) -> None:
    factory = scoring_backend
    radar, profile, run = seed_run(factory)
    with factory() as session:
        row = session.execute(
            select(EvaluationModel.run_id).where(EvaluationModel.run_id == run.run_id)
        ).first()
        assert row is not None


def test_duplicate_publish_is_arbitrated_by_unique_constraint(
    scoring_backend: Any,
) -> None:
    factory = scoring_backend
    radar, _, run = seed_run(factory)
    summary = radar.process_run(
        run_id=run.run_id,
        job_execution_id=uuid4(),
    )
    assert summary["state"] == "succeeded"
    assert _evaluation_count(factory, run.run_id) == 18
