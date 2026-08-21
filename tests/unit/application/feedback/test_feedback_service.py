"""FeedbackService.record_feedback: idempotency, supersede, terminal, reasons."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from tests.support.feedback import FeedbackTestContext

from umbral.application.feedback.contracts import (
    FeedbackInvalidReason,
    FeedbackNotAccessible,
    FeedbackRecord,
    FeedbackTerminal,
    FeedbackValidationError,
)
from umbral.application.radar.contracts import SearchProfile


def _record(
    ctx: FeedbackTestContext,
    profile: SearchProfile,
    event_type: str,
    **overrides: Any,
) -> FeedbackRecord:
    kwargs: dict[str, Any] = {
        "owner_id": profile.owner_id,
        "profile_id": profile.profile_id,
        "listing_id": uuid4(),
        "run_id": None,
        "event_type": event_type,
        "reason_keys": (),
        "idempotency_key": str(uuid4()),
        "correlation_id": uuid4(),
    }
    kwargs.update(overrides)
    return ctx.service.record_feedback(**kwargs)


def test_records_an_immutable_event_with_context() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    record = _record(ctx, profile, "like")
    assert record.event.event_type == "like"
    assert record.event.profile_id == profile.profile_id
    assert record.event.state == "active"
    assert record.decision_state == "like"
    assert record.superseded is False
    assert record.noop is False
    assert len(ctx.events.rows) == 1


def test_replay_with_same_idempotency_key_returns_existing_event() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    first = _record(ctx, profile, "save")
    replay = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=first.event.listing_id,
        run_id=None,
        event_type="dismiss",
        reason_keys=(),
        idempotency_key=first.event.idempotency_key,
        correlation_id=uuid4(),
    )
    assert replay.event.event_id == first.event.event_id
    assert replay.noop is True
    assert len(ctx.events.rows) == 1


def test_same_active_type_is_an_idempotent_noop() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    first = _record(ctx, profile, "save")
    second = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=first.event.listing_id,
        run_id=None,
        event_type="save",
        reason_keys=(),
        idempotency_key=str(uuid4()),
        correlation_id=uuid4(),
    )
    assert second.noop is True
    assert second.event.event_id == first.event.event_id
    assert len(ctx.events.rows) == 1


def test_decision_change_supersedes_with_compensation() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    first = _record(ctx, profile, "like")
    second = _record(ctx, profile, "dislike", listing_id=first.event.listing_id)
    third = _record(ctx, profile, "like", listing_id=first.event.listing_id)
    assert second.superseded is True
    assert second.event.superseded_by == first.event.event_id
    assert third.superseded is True
    active = ctx.events.active_state(profile.profile_id, first.event.listing_id)
    assert active is not None and active.event_type == "like"
    assert len(ctx.events.rows) == 3


def test_contacted_is_terminal() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    _record(ctx, profile, "contacted")
    listing = ctx.events.rows[0].listing_id
    with pytest.raises(FeedbackTerminal):
        _record(ctx, profile, "like", listing_id=listing)


def test_unknown_event_type_is_rejected() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    with pytest.raises(FeedbackValidationError):
        _record(ctx, profile, "flag")


def test_unknown_reason_key_is_rejected() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    with pytest.raises(FeedbackInvalidReason):
        _record(ctx, profile, "dislike", reason_keys=("ghost",))


def test_reason_not_allowed_for_event_type_is_rejected() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    with pytest.raises(FeedbackInvalidReason):
        _record(ctx, profile, "like", reason_keys=("price_too_high",))


def test_reason_with_unregistered_concept_is_rejected() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    ctx.concepts.rows.clear()
    with pytest.raises(FeedbackInvalidReason):
        _record(ctx, profile, "dislike", reason_keys=("rooms_wrong",))


def test_cross_owner_access_is_denied() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile(owner_id=uuid4())
    with pytest.raises(FeedbackNotAccessible):
        _record(ctx, profile, "save", owner_id=uuid4())


def test_too_many_reasons_is_rejected() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    with pytest.raises(FeedbackValidationError):
        _record(
            ctx,
            profile,
            "dislike",
            reason_keys=(
                "rooms_wrong",
                "building_state",
                "lighting_bad",
                "surface_wrong",
                "location_no",
                "price_too_high",
            ),
        )


def test_save_records_and_upserts_the_shortlist() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    record = _record(ctx, profile, "save")
    assert ctx.shortlists.list_for_profile(profile.profile_id) == (
        record.event.listing_id,
    )


def test_leaving_save_removes_from_the_shortlist() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    saved = _record(ctx, profile, "save")
    _record(ctx, profile, "dismiss", listing_id=saved.event.listing_id)
    assert ctx.shortlists.list_for_profile(profile.profile_id) == ()


def test_recording_emits_feedback_recorded_event_without_text() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    _record(ctx, profile, "like", reason_keys=("price_fits",))
    recorded = [
        event
        for event in ctx.events_out.events
        if event.event_type == "feedback.recorded.v1"
    ]
    assert len(recorded) == 1
    assert recorded[0].payload["reason_count"] == 1
    assert recorded[0].payload["concept_reason_count"] == 0
    assert recorded[0].payload["has_free_feedback"] is False
    assert "free_feedback" not in recorded[0].payload


def test_free_feedback_is_disabled_by_default() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    with pytest.raises(FeedbackValidationError):
        _record(ctx, profile, "like", free_feedback="me gusta")


def test_free_feedback_enabled_respects_length_limit() -> None:
    ctx = FeedbackTestContext(free_feedback_enabled=True, max_free_feedback_length=5)
    profile = ctx.add_profile()
    with pytest.raises(FeedbackValidationError):
        _record(ctx, profile, "like", free_feedback="demasiado largo")
    record = _record(ctx, profile, "like", free_feedback="ok")
    assert record.event.free_feedback == "ok"
