"""Recalculado integration: confirm/undo create edited runs; direct feedback never does."""
# ruff: noqa: E501

from __future__ import annotations

from typing import Any
from uuid import uuid4

from tests.integration.criteria.conftest import seed_silver_listings
from tests.integration.feedback.conftest import (
    build_criteria,
    build_feedback,
    build_radar,
    seed_concepts,
    seed_user,
)

from umbral.application.radar.contracts import SearchProfile
from umbral.infrastructure.db.repositories.radar import SqlAlchemyRunRepository


def _radar_profile(feedback_backend: Any, radar: Any) -> tuple[Any, SearchProfile]:
    owner_id = seed_user(feedback_backend)
    profile = radar.create_profile(
        owner_id=owner_id,
        name="Mi radar",
        zones=("caballito",),
        budget_max=600000.0,
        budget_min=None,
        min_rooms=2,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )[0]
    return owner_id, profile


def test_confirmed_learning_creates_an_edited_run(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    criteria = build_criteria(feedback_backend)
    radar = build_radar(feedback_backend)
    feedback = build_feedback(feedback_backend, radar=radar, criteria=criteria)
    owner_id, profile = _radar_profile(feedback_backend, radar)
    listings = seed_silver_listings(feedback_backend, count=3)
    for listing in listings:
        feedback.record_feedback(
            owner_id=owner_id,
            profile_id=profile.profile_id,
            listing_id=listing,
            run_id=None,
            event_type="dislike",
            reason_keys=("rooms_wrong",),
            idempotency_key=str(uuid4()),
            correlation_id=uuid4(),
        )
    proposals, _ = feedback.list_proposals(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        state="pending",
        after=None,
        limit=25,
    )
    result = feedback.confirm_proposal(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        proposal_id=proposals[0].proposal_id,
        correlation_id=uuid4(),
    )
    runs = SqlAlchemyRunRepository(feedback_backend)
    assert result.run_id is not None
    run = runs.get(result.run_id)
    assert run is not None
    assert run.trigger == "edited"
    assert run.profile_version_id is not None


def test_direct_feedback_never_creates_runs(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    criteria = build_criteria(feedback_backend)
    radar = build_radar(feedback_backend)
    feedback = build_feedback(feedback_backend, radar=radar, criteria=criteria)
    owner_id, profile = _radar_profile(feedback_backend, radar)
    listing = seed_silver_listings(feedback_backend, count=1)[0]
    runs = SqlAlchemyRunRepository(feedback_backend)
    before = runs.latest_for_profile(profile.profile_id)
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing,
        run_id=None,
        event_type="like",
        reason_keys=("price_fits",),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    after = runs.latest_for_profile(profile.profile_id)
    assert (after.run_id if after is not None else None) == (
        before.run_id if before is not None else None
    )
