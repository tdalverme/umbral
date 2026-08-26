"""Pure, deterministic V5 policy: authorization and planning.

The policy consumes typed acts from ``TurnInterpretationV5`` and returns one
decision per act plus the planned command payloads. It never inspects generic
dictionaries, never guesses targets, and produces no durable commands for
``Query`` or ``UnsupportedRequest``.
"""

from __future__ import annotations

from umbral.application.conversation.v5.contracts import (
    ActDecisionV5,
    ClearFilter,
    ClearFilterCommand,
    CommandV5,
    ConversationActV5,
    CreateRadar,
    CreateRadarCommand,
    ExpressDesire,
    Query,
    RecordFeedback,
    ResolvePending,
    ReviseDesire,
    SetFilter,
    SetFilterCommand,
    TurnContextV5,
    TurnInterpretationV5,
    TurnPlanV5,
    UnsupportedRequest,
    WithdrawDesire,
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


def plan_turn_v5(
    *,
    user_message: str,
    context: TurnContextV5,
    interpretation: TurnInterpretationV5,
) -> TurnPlanV5:
    """Plan every typed act into exactly one deterministic decision."""
    decisions: list[ActDecisionV5] = []
    commands: list[CommandV5] = []
    for act in interpretation.acts:
        decision, command = _decide(act, user_message, context, interpretation.acts)
        decisions.append(decision)
        if command is not None:
            commands.append(command)
    return TurnPlanV5(decisions=tuple(decisions), commands=tuple(commands))


def _decide(
    act: ConversationActV5,
    user_message: str,
    context: TurnContextV5,
    acts: tuple[ConversationActV5, ...],
) -> tuple[ActDecisionV5, CommandV5 | None]:
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
                    ActDecisionV5(
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
            current = _current_filter(context, act.filter_key)
            if current is None or current == act.value:
                return _applied(act.act_id), command
            return _pending(act.act_id, "filter.changes_existing_hard_filter"), command
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
            return _pending(act.act_id, "filter.removes_hard_filter"), clear_command
        case ExpressDesire():
            return _applied(act.act_id), None
        case ReviseDesire():
            if not context.authorizes(act.desire_ref):
                return _rejected(act.act_id, "desire.not_active"), None
            return _applied(act.act_id), None
        case WithdrawDesire():
            if not context.authorizes(act.desire_ref):
                return _rejected(act.act_id, "desire.not_active"), None
            return _applied(act.act_id), None
        case RecordFeedback():
            if not context.authorizes(act.listing_ref):
                return _rejected(act.act_id, "feedback.listing_not_authorized"), None
            return _applied(act.act_id), None
        case ResolvePending():
            if not context.authorizes(act.pending_ref):
                return _rejected(act.act_id, "pending.not_found"), None
            return _applied(act.act_id), None
    return _rejected(act.act_id, "act.unknown_kind"), None


def _applied(act_id: str) -> ActDecisionV5:
    return ActDecisionV5(act_id, "applied")


def _rejected(act_id: str, reason_code: str) -> ActDecisionV5:
    return ActDecisionV5(act_id, "rejected", reason_code)


def _pending(act_id: str, reason_code: str) -> ActDecisionV5:
    return ActDecisionV5(act_id, "pending", reason_code)


def _has_untrusted_evidence(act: ConversationActV5, context: TurnContextV5) -> bool:
    untrusted = {item.text for item in context.untrusted_content}
    if not untrusted:
        return False
    return any(span.text in untrusted for span in act.evidence_spans)


def _has_explicit_evidence(act: ConversationActV5, user_message: str) -> bool:
    if not act.evidence_spans:
        return False
    return all(
        0 <= span.start <= span.end <= len(user_message)
        and user_message[span.start : span.end] == span.text
        for span in act.evidence_spans
    )


def _has_mutation(acts: tuple[ConversationActV5, ...]) -> bool:
    return any(act.kind in _MUTATION_KINDS for act in acts)


def _current_filter(
    context: TurnContextV5, filter_key: str
) -> object | None:
    for filter_view in context.current_filters:
        if filter_view.filter_key == filter_key:
            return filter_view.value
    return None
