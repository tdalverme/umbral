"""Feedback lineage integration: proposals reference their feedback events."""
# ruff: noqa: E501

from __future__ import annotations

from typing import Any
from uuid import uuid4

from tests.integration.criteria.conftest import seed_silver_listings
from tests.integration.feedback.conftest import (
    build_feedback,
    seed_concepts,
    seed_profile,
    seed_user,
)


def test_proposal_lineage_references_feedback_events(feedback_backend: Any) -> None:
    seed_concepts(feedback_backend)
    feedback = build_feedback(feedback_backend)
    owner_id = seed_user(feedback_backend)
    profile = seed_profile(feedback_backend, owner_id)
    listings = seed_silver_listings(feedback_backend, count=3)
    recorded: list[str] = []
    for listing in listings:
        record = feedback.record_feedback(
            owner_id=owner_id,
            profile_id=profile.profile_id,
            listing_id=listing,
            run_id=None,
            event_type="dislike",
            reason_keys=("rooms_wrong",),
            idempotency_key=str(uuid4()),
            correlation_id=uuid4(),
        )
        recorded.append(str(record.event.event_id))
    proposals, _ = feedback.list_proposals(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        state="pending",
        after=None,
        limit=25,
    )
    assert len(proposals) == 1
    evidence_ids = {
        str(ref["feedback_event_id"]) for ref in proposals[0].evidence_refs
    }
    assert evidence_ids == set(recorded)
    # Every evidence ref resolves to a persisted active feedback event.
    persisted = feedback.events.active_for_profile(profile.profile_id)
    persisted_ids = {str(item.event_id) for item in persisted}
    for ref in proposals[0].evidence_refs:
        assert ref["feedback_event_id"] in persisted_ids, ref["feedback_event_id"]
