"""Pure, deterministic V5 policy: authorization and planning.

The policy consumes typed acts from ``TurnInterpretationV5`` and returns one
decision per act plus the planned command payloads. It never inspects generic
dictionaries, never guesses targets, and produces no durable commands for
``Query`` or ``UnsupportedRequest``. Commands are intentionally uninhabited
until Task 6 publishes the closed command union.
"""

from __future__ import annotations

from umbral.application.conversation.v5.contracts import (
    ActDecisionV5,
    ClearFilter,
    ConversationActV5,
    CreateRadar,
    ExpressDesire,
    Query,
    RecordFeedback,
    ResolvePending,
    ReviseDesire,
    SetFilter,
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
    decisions = tuple(
        _decide(act, user_message, context, interpretation.acts)
        for act in interpretation.acts
    )
    return TurnPlanV5(decisions=decisions, commands=())


def _decide(
    act: ConversationActV5,
    user_message: str,
    context: TurnContextV5,
    acts: tuple[ConversationActV5, ...],
) -> ActDecisionV5:
    if act.kind not in context.allowed_capabilities:
        return _rejected(act.act_id, "capability.not_allowed")
    if _has_untrusted_evidence(act, context):
        return _rejected(act.act_id, "act.untrusted_evidence")
    if not _has_explicit_evidence(act, user_message):
        return _rejected(act.act_id, "act.missing_evidence")
    match act:
        case Query():
            if _has_mutation(acts):
                return ActDecisionV5(
                    act.act_id, "needs_clarification", "act.query_with_mutation"
                )
            return _applied(act.act_id)
        case UnsupportedRequest():
            return _rejected(act.act_id, "request.unsupported")
        case CreateRadar():
            if context.active_radar_ref is not None:
                return _rejected(act.act_id, "radar.already_bound")
            return _applied(act.act_id)
        case SetFilter():
            current = _current_filter(context, act.filter_key)
            if current is None or current == act.value:
                return _applied(act.act_id)
            return _pending(act.act_id, "filter.changes_existing_hard_filter")
        case ClearFilter():
            if _current_filter(context, act.filter_key) is None:
                return _rejected(act.act_id, "filter.not_active")
            return _pending(act.act_id, "filter.removes_hard_filter")
        case ExpressDesire():
            return _applied(act.act_id)
        case ReviseDesire():
            if not context.authorizes(act.desire_ref):
                return _rejected(act.act_id, "desire.not_active")
            return _applied(act.act_id)
        case WithdrawDesire():
            if not context.authorizes(act.desire_ref):
                return _rejected(act.act_id, "desire.not_active")
            return _applied(act.act_id)
        case RecordFeedback():
            if not context.authorizes(act.listing_ref):
                return _rejected(act.act_id, "feedback.listing_not_authorized")
            return _applied(act.act_id)
        case ResolvePending():
            if not context.authorizes(act.pending_ref):
                return _rejected(act.act_id, "pending.not_found")
            return _applied(act.act_id)
    return _rejected(act.act_id, "act.unknown_kind")


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
