"""FeedbackService decision-items: shortlist/dismissed listing, save/un-save."""

from __future__ import annotations

from uuid import UUID, uuid4

from tests.support.feedback import FeedbackTestContext

from umbral.application.radar.contracts import SearchProfile


def _record(
    ctx: FeedbackTestContext,
    profile: SearchProfile,
    event_type: str,
    listing_id: UUID,
) -> object:
    return ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_id,
        run_id=None,
        event_type=event_type,
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )


def test_decision_items_filter_by_state() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    saved = [uuid4(), uuid4()]
    dismissed = uuid4()
    for listing in saved:
        _record(ctx, profile, "save", listing)
    _record(ctx, profile, "dismiss", dismissed)
    saved_items, _ = ctx.service.list_decision_items(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        decision_state="save",
        after=None,
        limit=25,
    )
    assert {item.listing_id for item in saved_items} == set(saved)
    dismissed_items, _ = ctx.service.list_decision_items(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        decision_state="dismiss",
        after=None,
        limit=25,
    )
    assert {item.listing_id for item in dismissed_items} == {dismissed}


def test_decision_states_annotate_listings() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    listing = uuid4()
    _record(ctx, profile, "like", listing)
    states = ctx.service.decision_states(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_ids=(listing, uuid4()),
    )
    assert states[listing] == "like"


def test_save_then_dismiss_updates_shortlist() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    listing = uuid4()
    _record(ctx, profile, "save", listing)
    assert ctx.shortlists.list_for_profile(profile.profile_id) == (listing,)
    _record(ctx, profile, "dismiss", listing)
    assert ctx.shortlists.list_for_profile(profile.profile_id) == ()
