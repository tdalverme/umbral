# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Concept feedback signals feed the deterministic learning engine (FR-004).

Strength and confidence never modulate the counting: the policy decides
(min_signals, window, cooldown); they are preserved as evidence only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tests.support.feedback import FeedbackTestContext

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def _concept_feedback():
    return (
        {
            "concept_key": "tipo_cocina",
            "polarity": "negative",
            "strength": "strong",
            "confidence": 0.9,
        },
    )


def test_concept_feedback_persists_strength_and_confidence_as_evidence() -> None:
    ctx = FeedbackTestContext(free_feedback_enabled=True)
    profile = ctx.add_profile()
    record = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-1",
        correlation_id=uuid4(),
        concept_feedback=_concept_feedback(),
        free_feedback="la cocina es chica e integrada",
    )
    assert record.noop is False
    assert len(record.event.concept_feedback) == 1
    signal = record.event.concept_feedback[0]
    assert signal.concept_key == "tipo_cocina"
    assert signal.polarity == "negative"
    assert signal.strength == "strong"
    assert signal.confidence == 0.9
    assert record.event.free_feedback == "la cocina es chica e integrada"


def test_concept_feedback_rejects_unknown_concepts() -> None:
    from umbral.application.feedback.contracts import FeedbackValidationError

    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    with pytest.raises(FeedbackValidationError) as exc:
        ctx.service.record_feedback(
            owner_id=profile.owner_id,
            profile_id=profile.profile_id,
            listing_id=uuid4(),
            run_id=None,
            event_type="dislike",
            reason_keys=(),
            idempotency_key="k-1",
            correlation_id=uuid4(),
            concept_feedback=(
                {
                    "concept_key": "palier_raro",
                    "polarity": "negative",
                    "strength": "low",
                    "confidence": 0.5,
                },
            ),
        )
    assert exc.value.error_codes[0] == "feedback.unknown_concept:palier_raro"


def test_concept_reasons_count_in_emitted_event() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-1",
        correlation_id=uuid4(),
        concept_feedback=_concept_feedback(),
    )
    recorded = [
        event
        for event in ctx.events_out.events
        if event.event_type == "feedback.recorded.v1"
    ]
    assert recorded[0].payload["concept_reason_count"] == 1
    assert recorded[0].payload["reason_count"] == 0


def test_two_consistent_signals_produce_a_pending_proposal() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    listing = ctx.events.rows[0].listing_id if ctx.events.rows else None
    ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-1",
        correlation_id=uuid4(),
        concept_feedback=_concept_feedback(),
    )
    second = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4() if listing is None else listing,
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-2",
        correlation_id=uuid4(),
        concept_feedback=_concept_feedback(),
    )
    assert second.learning_proposal_id is not None
    proposal = ctx.proposals.get(second.learning_proposal_id)
    assert proposal is not None
    assert proposal.state == "pending"
    assert proposal.change.concept_key == "tipo_cocina"
    assert proposal.change.polarity == "negative"
    assert len(proposal.evidence_refs) == 2


def test_conflicting_polarity_does_not_create_proposal_draft() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-1",
        correlation_id=uuid4(),
        concept_feedback=_concept_feedback(),
    )
    record = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="like",
        reason_keys=(),
        idempotency_key="k-2",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "tipo_cocina",
                "polarity": "positive",
                "strength": "medium",
                "confidence": 0.6,
            },
        ),
    )
    assert record.learning_proposal_id is None
    assert ctx.proposals.rows == []


def test_strength_does_not_modulate_signal_counting() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    base = _concept_feedback()
    weak_item = {
        "concept_key": "tipo_cocina",
        "polarity": "negative",
        "strength": "low",
        "confidence": 0.2,
    }
    ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-1",
        correlation_id=uuid4(),
        concept_feedback=(weak_item,),
    )
    record = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-2",
        correlation_id=uuid4(),
        concept_feedback=base,
    )
    assert record.learning_proposal_id is not None


def test_window_expiry_leaves_no_proposal_draft() -> None:
    ctx = FeedbackTestContext()
    profile = ctx.add_profile()
    old = NOW - timedelta(days=120)
    ctx.events.rows.append(
        _event_with_signals(ctx, profile, old, "k-old")
    )
    record = ctx.service.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-new",
        correlation_id=uuid4(),
        concept_feedback=_concept_feedback(),
    )
    assert record.learning_proposal_id is None


def _event_with_signals(ctx: FeedbackTestContext, profile, created_at, key):
    from umbral.application.feedback.contracts import FeedbackEvent

    event = FeedbackEvent(
        event_id=uuid4(),
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        state="active",
        superseded_by=None,
        idempotency_key=key,
        reasons=(),
        free_feedback=None,
        created_at=created_at,
        correlation_id=uuid4(),
    )
    event = _with_concept(event, "tipo_cocina", "negative", "low", 0.2)
    return event


def _with_concept(event, key, polarity, strength, confidence):
    from dataclasses import replace

    from umbral.application.feedback.contracts import ConceptFeedback

    return replace(
        event,
        concept_feedback=(
            ConceptFeedback(
                concept_key=key,
                polarity=polarity,
                strength=strength,
                confidence=confidence,
            ),
        ),
    )
