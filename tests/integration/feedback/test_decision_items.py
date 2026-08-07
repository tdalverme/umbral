"""Decision-items integration: shortlist/dismissed views, no runs on direct feedback."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from tests.integration.criteria.conftest import seed_silver_listings
from tests.integration.feedback.conftest import (
    build_feedback,
    seed_profile,
    seed_user,
)


def test_decision_items_filter_by_state_and_persist(feedback_backend: Any) -> None:
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listings = seed_silver_listings(feedback_backend, count=3)
    for listing in listings[:2]:
        feedback.record_feedback(
            owner_id=owner_id,
            profile_id=profile.profile_id,
            listing_id=listing,
            run_id=None,
            event_type="save",
            reason_keys=(),
            idempotency_key=str(uuid4()),
            correlation_id=uuid4(),
        )
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=listings[2],
        run_id=None,
        event_type="dismiss",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    saved, _ = feedback.list_decision_items(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        decision_state="save",
        after=None,
        limit=25,
    )
    assert {item.listing_id for item in saved} == set(listings[:2])
    dismissed, _ = feedback.list_decision_items(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        decision_state="dismiss",
        after=None,
        limit=25,
    )
    assert {item.listing_id for item in dismissed} == {listings[2]}


def test_direct_feedback_creates_no_runs(feedback_backend: Any) -> None:
    from umbral.infrastructure.db.repositories.radar import SqlAlchemyRunRepository

    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listing = seed_silver_listings(feedback_backend, count=1)[0]
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
    runs = SqlAlchemyRunRepository(feedback_backend)
    assert runs.latest_for_profile(profile.profile_id) is None
