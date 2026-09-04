"""Unit tests for V5 contextual listing feedback policy."""

from __future__ import annotations

from uuid import UUID

from umbral.application.conversation.contracts import (
    ConversationAct,
    EvidenceSpan,
    RecordFeedback,
    RecordFeedbackCommand,
    TurnContext,
    TurnInterpretation,
)
from umbral.application.conversation.policy import plan_turn

LISTING_ID = UUID(int=13)


def _context(
    *, listing_refs: tuple[str, ...] = (f"listing:{LISTING_ID}",)
) -> TurnContext:
    return TurnContext(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=listing_refs,
        allowed_capabilities=(
            "record_feedback",
            "query",
        ),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id="correlation:1",
    )


def _interpretation(*acts: ConversationAct) -> TurnInterpretation:
    return TurnInterpretation(
        model_version="gpt-4.1-mini",
        prompt_version="interpretation",
        acts=acts,
    )


def _feedback(listing_ref: str) -> RecordFeedback:
    message = "No me gusta"
    return RecordFeedback(
        act_id="a1",
        confidence=0.9,
        evidence_spans=(EvidenceSpan(start=0, end=len(message), text=message),),
        listing_ref=listing_ref,
        feedback_type="dislike",
        raw_text=message,
    )


def test_feedback_uses_verified_focused_listing() -> None:
    plan = plan_turn(
        user_message="No me gusta",
        context=_context(),
        interpretation=_interpretation(_feedback(f"listing:{LISTING_ID}")),
    )

    assert plan.decisions[0].status == "applied"
    assert plan.commands == (
        RecordFeedbackCommand(
            act_id="a1",
            listing_id=LISTING_ID,
            feedback_type="dislike",
            raw_text="No me gusta",
        ),
    )


def test_feedback_with_missing_or_foreign_listing_ref_is_rejected() -> None:
    plan = plan_turn(
        user_message="No me gusta",
        context=_context(listing_refs=()),
        interpretation=_interpretation(_feedback("listing:foreign")),
    )

    assert plan.decisions[0].status == "rejected"
    assert plan.decisions[0].reason_code == "feedback.listing_not_authorized"
    assert plan.commands == ()


def test_feedback_type_is_published_and_bounded() -> None:
    message = "Guarda este"
    plan = plan_turn(
        user_message=message,
        context=_context(),
        interpretation=_interpretation(
            RecordFeedback(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=len(message), text=message),
                ),
                listing_ref=f"listing:{LISTING_ID}",
                feedback_type="save",
            )
        ),
    )

    assert plan.decisions[0].status == "applied"
    assert plan.commands == (
        RecordFeedbackCommand(
            act_id="a1",
            listing_id=LISTING_ID,
            feedback_type="save",
            raw_text=None,
        ),
    )
