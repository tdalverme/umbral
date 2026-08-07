"""Feedback integration: immutable chains, idempotency, terminal, shortlist."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from tests.integration.criteria.conftest import seed_silver_listings
from tests.integration.feedback.conftest import (
    build_feedback,
    seed_profile,
    seed_user,
)

from umbral.application.feedback.contracts import (
    FeedbackTerminal,
    FeedbackValidationError,
)


def test_decision_change_supersedes_and_state_is_unique(feedback_backend: Any) -> None:
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listing_id = seed_silver_listings(feedback_backend, count=1)[0]

    first = feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
        run_id=None,
        event_type="like",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    second = feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    assert second.superseded is True
    assert second.event.superseded_by == first.event.event_id
    state = feedback.decision_state(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
    )
    assert state.decision_state == "dislike"


def test_replay_same_idempotency_key_does_not_duplicate(feedback_backend: Any) -> None:
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listing_id = seed_silver_listings(feedback_backend, count=1)[0]
    key = str(uuid4())
    first = feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
        run_id=None,
        event_type="save",
        reason_keys=(),
        idempotency_key=key,
        correlation_id=uuid4(),
    )
    replay = feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
        run_id=None,
        event_type="dismiss",
        reason_keys=(),
        idempotency_key=key,
        correlation_id=uuid4(),
    )
    assert replay.event.event_id == first.event.event_id
    assert replay.noop is True
    actives = feedback.events.active_for_profile(profile.profile_id)
    assert len(actives) == 1


def test_contacted_is_terminal_over_real_db(feedback_backend: Any) -> None:
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listing_id = seed_silver_listings(feedback_backend, count=1)[0]
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
        run_id=None,
        event_type="contacted",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    with pytest.raises(FeedbackTerminal):
        feedback.record_feedback(
            owner_id=owner_id,
            profile_id=profile.profile_id,
            listing_id=listing_id,
            run_id=None,
            event_type="like",
            reason_keys=(),
            idempotency_key=str(uuid4()),
            correlation_id=uuid4(),
        )


def test_save_upserts_the_shared_shortlist(feedback_backend: Any) -> None:
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listings = seed_silver_listings(feedback_backend, count=2)
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listings[0],
        run_id=None,
        event_type="save",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listings[1],
        run_id=None,
        event_type="save",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    assert set(feedback.shortlists.list_for_profile(profile.profile_id)) == set(
        listings
    )
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listings[0],
        run_id=None,
        event_type="dismiss",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    assert feedback.shortlists.list_for_profile(profile.profile_id) == (
        listings[1],
    )


def test_invalid_reason_is_rejected_over_real_db(feedback_backend: Any) -> None:
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listing_id = seed_silver_listings(feedback_backend, count=1)[0]
    with pytest.raises(FeedbackValidationError):
        feedback.record_feedback(
            owner_id=owner_id,
            profile_id=profile.profile_id,
            listing_id=listing_id,
            run_id=None,
            event_type="dislike",
            reason_keys=("ghost",),
            idempotency_key=str(uuid4()),
            correlation_id=uuid4(),
        )
