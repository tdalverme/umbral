"""Integration: evaluation lineage and comparison shortlists over real Postgres."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from tests.integration.scoring.conftest import build_scoring, seed_run

from umbral.infrastructure.db.models.criteria import (
    ListingObservation as ObservationModel,
)
from umbral.infrastructure.db.models.scoring import (
    ComparisonShortlist as ShortlistModel,
)
from umbral.infrastructure.db.models.scoring import (
    CriterionEvaluation as EvaluationModel,
)


def test_evaluation_lineage_walks_to_observations_and_snapshots(
    scoring_backend: Any,
) -> None:
    factory = scoring_backend
    _, profile, run = seed_run(factory)
    with factory() as session:
        evaluations = session.scalars(
            select(EvaluationModel).where(EvaluationModel.run_id == run.run_id)
        )
        evaluation = next(
            (
                item
                for item in evaluations
                if item.input_refs and item.input_refs[0].get("kind") == "observation"
            ),
            None,
        )
        assert evaluation is not None
        observation_id = evaluation.input_refs[0]["ref"]
        observation = session.get(ObservationModel, observation_id)
        assert observation is not None
        assert observation.extraction_version_id is not None
        assert observation.state == "active"


def test_shortlist_replaces_idempotently(scoring_backend: Any) -> None:
    factory = scoring_backend
    _, profile, run = seed_run(factory)
    scoring = build_scoring(factory, comparator_enabled=True)
    item_ids = scoring.items.listing_ids_for_run(run.run_id)
    assert len(item_ids) >= 2
    scoring.set_shortlist(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_ids=item_ids[:2],
        correlation_id=uuid4(),
    )
    assert (
        scoring.get_shortlist(owner_id=profile.owner_id, profile_id=profile.profile_id)
        == item_ids[:2]
    )
    scoring.set_shortlist(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_ids=(item_ids[0],),
        correlation_id=uuid4(),
    )
    assert scoring.get_shortlist(
        owner_id=profile.owner_id, profile_id=profile.profile_id
    ) == (item_ids[0],)
    with factory() as session:
        count = session.scalar(
            select(ShortlistModel.id).where(
                ShortlistModel.profile_id == profile.profile_id
            )
        )
        assert count is not None


def test_explanation_is_readable_after_run(scoring_backend: Any) -> None:
    factory = scoring_backend
    _, profile, run = seed_run(factory)
    scoring = build_scoring(factory)
    listing_id = scoring.items.listing_ids_for_run(run.run_id)[0]
    explanation = scoring.get_explanation(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        run_id=run.run_id,
        listing_id=listing_id,
    )
    assert explanation.score_version == "scoring-policy-v1"
    assert explanation.reasons
    assert all(reason.evidence_refs for reason in explanation.reasons)
