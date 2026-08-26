"""Unit tests for V5 desire preservation policy."""

from __future__ import annotations

from umbral.application.conversation.v5.contracts import (
    ConversationActV5,
    DesireViewV5,
    EvidenceSpan,
    ExpressDesire,
    RecordDesireCommand,
    ReviseDesire,
    ReviseDesireCommand,
    TurnContextV5,
    TurnInterpretationV5,
    WithdrawDesire,
    WithdrawDesireCommand,
)
from umbral.application.conversation.v5.policy import plan_turn_v5


def _desire(ref: str, subject: str = "moderno") -> DesireViewV5:
    return DesireViewV5(
        desire_ref=ref,
        raw_text="Quiero algo moderno",
        subject_ref=subject,
        concept_links=(),
    )


def _context(*, desires: tuple[DesireViewV5, ...] = ()) -> TurnContextV5:
    return TurnContextV5(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=desires,
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=(
            "create_radar",
            "set_filter",
            "clear_filter",
            "express_desire",
            "revise_desire",
            "withdraw_desire",
            "record_feedback",
            "resolve_pending",
            "query",
            "unsupported_request",
        ),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id="correlation:1",
    )


def _interpretation(*acts: ConversationActV5) -> TurnInterpretationV5:
    return TurnInterpretationV5(
        model_version="gpt-4.1-mini",
        prompt_version="interpretation-v5",
        acts=acts,
    )


def test_express_desire_with_zero_concept_links_plans_persistence() -> None:
    plan = plan_turn_v5(
        user_message="Quiero algo moderno",
        context=_context(),
        interpretation=_interpretation(
            ExpressDesire(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=19, text="Quiero algo moderno"),
                ),
                raw_text="Quiero algo moderno",
                subject_ref="moderno",
                concept_links=(),
            )
        ),
    )

    assert plan.decisions[0].status == "applied"
    assert plan.commands == (
        RecordDesireCommand(
            act_id="a1",
            raw_text="Quiero algo moderno",
            subject_ref="moderno",
            concept_links=(),
        ),
    )


def test_ambiguous_revision_requests_clarification() -> None:
    plan = plan_turn_v5(
        user_message="Cambiá ese deseo",
        context=_context(
            desires=(_desire("desire:1"), _desire("desire:2", subject="balcon"))
        ),
        interpretation=_interpretation(
            ReviseDesire(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=16, text="Cambiá ese deseo"),
                ),
                desire_ref=None,
                raw_text="Quiero algo moderno",
                concept_links=(),
            )
        ),
    )

    assert plan.decisions[0].status == "needs_clarification"
    assert plan.decisions[0].reason_code == "desire.ambiguous"
    assert plan.commands == ()


def test_revision_without_active_desire_is_rejected() -> None:
    plan = plan_turn_v5(
        user_message="Cambiá ese deseo",
        context=_context(desires=()),
        interpretation=_interpretation(
            ReviseDesire(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=16, text="Cambiá ese deseo"),
                ),
                desire_ref="desire:foreign",
                raw_text="Quiero algo moderno",
                concept_links=(),
            )
        ),
    )

    assert plan.decisions[0].status == "rejected"
    assert plan.decisions[0].reason_code == "desire.not_active"
    assert plan.commands == ()


def test_revision_with_single_active_desire_targets_it() -> None:
    message = "Ahora prefiero con balcón"
    plan = plan_turn_v5(
        user_message=message,
        context=_context(desires=(_desire("desire:1"),)),
        interpretation=_interpretation(
            ReviseDesire(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=len(message), text=message),
                ),
                desire_ref="desire:1",
                raw_text=message,
                concept_links=(),
            )
        ),
    )

    assert plan.decisions[0].status == "applied"
    assert plan.commands == (
        ReviseDesireCommand(
            act_id="a1",
            desire_ref="desire:1",
            raw_text=message,
            concept_links=(),
        ),
    )


def test_withdraw_single_active_desire_plans_command() -> None:
    message = "Ya no quiero balcón"
    plan = plan_turn_v5(
        user_message=message,
        context=_context(desires=(_desire("desire:1", subject="balcon"),)),
        interpretation=_interpretation(
            WithdrawDesire(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(
                    EvidenceSpan(start=0, end=len(message), text=message),
                ),
                desire_ref="desire:1",
            )
        ),
    )

    assert plan.decisions[0].status == "applied"
    assert plan.commands == (
        WithdrawDesireCommand(act_id="a1", desire_ref="desire:1"),
    )
