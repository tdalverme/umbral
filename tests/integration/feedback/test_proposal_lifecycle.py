"""Learning proposal lifecycle integration: signals, confirm, undo, recalc."""
# ruff: noqa: E501

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from tests.integration.criteria.conftest import seed_silver_listings
from tests.integration.feedback.conftest import (
    build_criteria,
    build_feedback,
    build_radar,
    seed_concepts,
    seed_profile,
    seed_user,
)

from umbral.application.feedback.contracts import ProposalNotPending
from umbral.application.radar.contracts import SearchProfile


def _profile_with_radar(feedback_backend: Any, radar: Any) -> tuple[Any, SearchProfile]:
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


def test_two_reasoned_dislikes_create_a_pending_proposal(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listings = seed_silver_listings(feedback_backend, count=2)
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
    assert len(proposals) == 1
    assert proposals[0].change.concept_key == "ambientes"
    assert proposals[0].change.polarity == "negative"
    assert len(proposals[0].evidence_refs) == 2


def test_one_reasoned_dislike_does_not_propose(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listings = seed_silver_listings(feedback_backend, count=1)
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
        state=None,
        after=None,
        limit=25,
    )
    assert proposals == ()


def test_confirm_applies_fact_versions_profile_and_submits_edited_run(
    feedback_backend: Any,
) -> None:
    seed_concepts(feedback_backend)
    criteria = build_criteria(feedback_backend)
    radar = build_radar(feedback_backend)
    feedback = build_feedback(feedback_backend, radar=radar, criteria=criteria)
    owner_id, profile = _profile_with_radar(feedback_backend, radar)
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
    assert len(proposals) == 1
    result = feedback.confirm_proposal(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        proposal_id=proposals[0].proposal_id,
        correlation_id=uuid4(),
    )
    assert result.applied_profile_version == 2
    facts = feedback.facts.active_for_profile(profile.profile_id)
    assert any(
        fact.concept_key == "ambientes" and fact.fact_source == "learning.proposal"
        for fact in facts
    )
    assert result.run_id is not None
    run = radar.runs.get(result.run_id)
    assert run is not None
    assert run.trigger == "edited"


def test_undo_records_compensation_and_submits_another_run(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    criteria = build_criteria(feedback_backend)
    radar = build_radar(feedback_backend)
    feedback = build_feedback(feedback_backend, radar=radar, criteria=criteria)
    owner_id, profile = _profile_with_radar(feedback_backend, radar)
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
    feedback.confirm_proposal(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        proposal_id=proposals[0].proposal_id,
        correlation_id=uuid4(),
    )
    undone = feedback.undo_proposal(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        proposal_id=proposals[0].proposal_id,
        correlation_id=uuid4(),
    )
    assert undone.state == "superseded"
    facts = feedback.facts.active_for_profile(profile.profile_id)
    assert any(fact.fact_source == "learning.undo" for fact in facts)


def test_confirming_non_pending_is_rejected(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    criteria = build_criteria(feedback_backend)
    radar = build_radar(feedback_backend)
    feedback = build_feedback(feedback_backend, radar=radar, criteria=criteria)
    owner_id, profile = _profile_with_radar(feedback_backend, radar)
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
    feedback.reject_proposal(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        proposal_id=proposals[0].proposal_id,
        correlation_id=uuid4(),
    )
    with pytest.raises(ProposalNotPending):
        feedback.confirm_proposal(
            owner_id=owner_id,
            profile_id=profile.profile_id,
            proposal_id=proposals[0].proposal_id,
            correlation_id=uuid4(),
        )
