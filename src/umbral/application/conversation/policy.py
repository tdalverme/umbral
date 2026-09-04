"""Pure, deterministic V5 policy: authorization and planning.

The policy consumes typed acts from ``TurnInterpretation`` and returns one
decision per act plus the planned command payloads. It never inspects generic
dictionaries, never guesses targets, and produces no durable commands for
``Query`` or ``UnsupportedRequest``.
"""

from __future__ import annotations

from uuid import UUID

from umbral.application.conversation.contracts import (
    ActDecision,
    ClearFilter,
    ClearFilterCommand,
    Command,
    ConversationAct,
    CreateRadar,
    CreateRadarCommand,
    ExpressDesire,
    Query,
    RecordDesireCommand,
    RecordFeedback,
    RecordFeedbackCommand,
    ResolvePending,
    ReviseDesire,
    ReviseDesireCommand,
    SetFilter,
    SetFilterCommand,
    TurnContext,
    TurnInterpretation,
    TurnPlan,
    UnsupportedRequest,
    WithdrawDesire,
    WithdrawDesireCommand,
)

_MUTATION_KINDS = frozenset(
    {
        "create_radar",
        "set_filter",
        "clear_filter",
        "express_desire",
        "revise_desire",
        "withdraw_desire",
        "record_feedback",
        "resolve_pending",
    }
)


def plan_turn(
    *,
    user_message: str,
    context: TurnContext,
    interpretation: TurnInterpretation,
) -> TurnPlan:
    """Plan every typed act into exactly one deterministic decision."""
    decisions: list[ActDecision] = []
    commands: list[Command] = []
    for act in interpretation.acts:
        decision, command = _decide(act, user_message, context, interpretation.acts)
        decisions.append(decision)
        if command is not None:
            commands.append(command)
    return TurnPlan(decisions=tuple(decisions), commands=tuple(commands))


def _decide(
    act: ConversationAct,
    user_message: str,
    context: TurnContext,
    acts: tuple[ConversationAct, ...],
) -> tuple[ActDecision, Command | None]:
    if act.kind not in context.allowed_capabilities:
        return _rejected(act.act_id, "capability.not_allowed"), None
    if _has_untrusted_evidence(act, context):
        return _rejected(act.act_id, "act.untrusted_evidence"), None
    if not _has_explicit_evidence(act, user_message):
        return _rejected(act.act_id, "act.missing_evidence"), None
    match act:
        case Query():
            if _has_mutation(acts):
                return (
                    ActDecision(
                        act.act_id,
                        "needs_clarification",
                        "act.query_with_mutation",
                    ),
                    None,
                )
            return _applied(act.act_id), None
        case UnsupportedRequest():
            return _rejected(act.act_id, "request.unsupported"), None
        case CreateRadar():
            if context.active_radar_ref is not None:
                return _rejected(act.act_id, "radar.already_bound"), None
            return (
                _applied(act.act_id),
                CreateRadarCommand(act_id=act.act_id, name=act.name),
            )
        case SetFilter():
            if context.active_radar_ref is None:
                return _rejected(act.act_id, "radar.not_bound"), None
            command = SetFilterCommand(
                act_id=act.act_id,
                filter_key=act.filter_key,
                value=act.value,
                expected_profile_version=context.active_radar_version,
            )
            return _pending(act.act_id, "filter.requires_confirmation"), command
        case ClearFilter():
            if context.active_radar_ref is None:
                return _rejected(act.act_id, "radar.not_bound"), None
            if _current_filter(context, act.filter_key) is None:
                return _rejected(act.act_id, "filter.not_active"), None
            clear_command = ClearFilterCommand(
                act_id=act.act_id,
                filter_key=act.filter_key,
                expected_profile_version=context.active_radar_version,
            )
            return _pending(act.act_id, "filter.requires_confirmation"), clear_command
        case ExpressDesire():
            return (
                _applied(act.act_id),
                RecordDesireCommand(
                    act_id=act.act_id,
                    raw_text=act.raw_text,
                    subject_ref=act.subject_ref,
                    concept_links=act.concept_links,
                ),
            )
        case ReviseDesire():
            target = _resolve_desire_ref(act.desire_ref, context)
            if target is None:
                return _rejected(act.act_id, "desire.not_active"), None
            if target == _AMBIGUOUS:
                return (
                    ActDecision(
                        act.act_id, "needs_clarification", "desire.ambiguous"
                    ),
                    None,
                )
            return (
                _applied(act.act_id),
                ReviseDesireCommand(
                    act_id=act.act_id,
                    desire_ref=target,
                    raw_text=act.raw_text,
                    concept_links=act.concept_links,
                ),
            )
        case WithdrawDesire():
            target = _resolve_desire_ref(act.desire_ref, context)
            if target is None:
                return _rejected(act.act_id, "desire.not_active"), None
            if target == _AMBIGUOUS:
                return (
                    ActDecision(
                        act.act_id, "needs_clarification", "desire.ambiguous"
                    ),
                    None,
                )
            return (
                _applied(act.act_id),
                WithdrawDesireCommand(act_id=act.act_id, desire_ref=target),
            )
        case RecordFeedback():
            if not context.authorizes(act.listing_ref):
                return _rejected(act.act_id, "feedback.listing_not_authorized"), None
            return (
                _applied(act.act_id),
                RecordFeedbackCommand(
                    act_id=act.act_id,
                    listing_id=UUID(act.listing_ref.removeprefix("listing:")),
                    feedback_type=act.feedback_type,
                    raw_text=act.raw_text,
                ),
            )
        case ResolvePending():
            if not context.authorizes(act.pending_ref):
                return _rejected(act.act_id, "pending.not_found"), None
            return _applied(act.act_id), None
    return _rejected(act.act_id, "act.unknown_kind"), None


def _applied(act_id: str) -> ActDecision:
    return ActDecision(act_id, "applied")


def _rejected(act_id: str, reason_code: str) -> ActDecision:
    return ActDecision(act_id, "rejected", reason_code)


def _pending(act_id: str, reason_code: str) -> ActDecision:
    return ActDecision(act_id, "pending", reason_code)


def _has_untrusted_evidence(act: ConversationAct, context: TurnContext) -> bool:
    untrusted = tuple(
        item.text for item in context.untrusted_content if item.text
    )
    return any(
        span.text == content or content in span.text
        for span in act.evidence_spans
        for content in untrusted
    )


def _has_explicit_evidence(act: ConversationAct, user_message: str) -> bool:
    if not act.evidence_spans:
        return False
    return all(
        0 <= span.start <= span.end <= len(user_message)
        and user_message[span.start : span.end] == span.text
        for span in act.evidence_spans
    )


def _has_mutation(acts: tuple[ConversationAct, ...]) -> bool:
    return any(act.kind in _MUTATION_KINDS for act in acts)


_AMBIGUOUS = "__ambiguous__"


def _resolve_desire_ref(
    desire_ref: str | None, context: TurnContext
) -> str | None:
    if desire_ref is not None:
        return desire_ref if context.authorizes(desire_ref) else None
    active = tuple(desire.desire_ref for desire in context.active_desires)
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        return _AMBIGUOUS
    return None


def _current_filter(
    context: TurnContext, filter_key: str
) -> object | None:
    for filter_view in context.current_filters:
        if filter_view.filter_key == filter_key:
            return filter_view.value
    return None
