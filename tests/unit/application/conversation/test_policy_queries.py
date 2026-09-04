"""Unit tests for the V5 safe read path and unsupported requests."""

from __future__ import annotations

from umbral.application.conversation.contracts import (
    ConversationAct,
    EvidenceSpan,
    Query,
    TurnContext,
    TurnInterpretation,
    UnsupportedRequest,
)
from umbral.application.conversation.policy import plan_turn


def _context() -> TurnContext:
    return TurnContext(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=(
            "query",
            "unsupported_request",
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


def test_query_produces_no_durable_command() -> None:
    plan = plan_turn(
        user_message="Mostrame mis matches",
        context=_context(),
        interpretation=_interpretation(
            Query(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=20, text="Mostrame mis matches"),
                ),
                query_text="Mostrame mis matches",
            )
        ),
    )

    assert plan.decisions[0].status == "applied"
    assert plan.commands == ()


def test_unsupported_request_is_never_approximated_as_withdrawal() -> None:
    plan = plan_turn(
        user_message="Borrá mi cuenta",
        context=_context(),
        interpretation=_interpretation(
            UnsupportedRequest(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=15, text="Borrá mi cuenta"),
                ),
                request_text="Borrá mi cuenta",
            )
        ),
    )

    assert plan.commands == ()
    assert plan.decisions[0].status == "rejected"
    assert plan.decisions[0].reason_code == "request.unsupported"
