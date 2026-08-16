"""Deterministic turn planning for the conversational copilot.

Turns acts into planned effects and routing decisions with no model authority:
soft, additive and reversible effects apply immediately; material or hard
changes to existing filters require a single confirmation (FR-011..FR-013,
FR-022, FR-024). This module is pure and never performs I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from umbral.application.conversation.contracts import (
    ConversationAct,
    ConversationContradiction,
    ConversationTurnContext,
    RoutingDecision,
    TurnEffect,
    TurnInterpretation,
    is_known_act_kind,
)

# Effect keys published by the reply schema v4 (status applied/pending/...).
EFFECT_RADAR_CREATED = "radar.created"
EFFECT_FILTER_SET = "filter.set"
EFFECT_FILTER_CLEARED = "filter.cleared"
EFFECT_PREFERENCE_REMEMBERED = "preference.remembered"
EFFECT_PREFERENCE_REVISED = "preference.revised"
EFFECT_PREFERENCE_WITHDRAWN = "preference.withdrawn"
EFFECT_FEEDBACK_RECORDED = "feedback.recorded"
EFFECT_PENDING_RESOLVED = "pending.resolved"
EFFECT_QUERY = "query"


@dataclass(frozen=True, slots=True)
class TurnPlan:
    """Planned effects, routing decision and optional single question."""

    effects: tuple[TurnEffect, ...]
    routing: RoutingDecision
    question: str | None = None


@dataclass(frozen=True, slots=True)
class _ActPlan:
    effects: tuple[TurnEffect, ...] = ()
    refresh_required: bool = False
    confirmation_required: bool = False
    question: str | None = None
    applied_filters: Mapping[str, Mapping[str, object]] | None = None


def plan_turn(
    *,
    interpretation: TurnInterpretation,
    context: ConversationTurnContext,
) -> TurnPlan:
    """Plan effects deterministically from validated acts.

    The planner never asks the model how to route; every branch below is fixed.
    """
    effects: list[TurnEffect] = []
    refresh_required = False
    confirmation_required = False
    question: str | None = None
    conflicts: list[str] = []

    seen_filters: dict[str, Mapping[str, object]] = dict(context.radar_filters or {})
    for act in interpretation.acts:
        plan = _plan_act(
            act=act,
            context=context,
            seen_filters=seen_filters,
            conflicts=conflicts,
        )
        effects.extend(plan.effects)
        refresh_required = refresh_required or plan.refresh_required
        confirmation_required = confirmation_required or plan.confirmation_required
        if plan.question is not None and question is None:
            question = plan.question
        if plan.applied_filters is not None:
            seen_filters.update(plan.applied_filters)

    if conflicts:
        raise ConversationContradiction(",".join(conflicts))

    return TurnPlan(
        effects=tuple(effects),
        routing=RoutingDecision(
            refresh_required=refresh_required,
            confirmation_required=confirmation_required,
        ),
        question=question,
    )


def _plan_act(
    *,
    act: ConversationAct,
    context: ConversationTurnContext,
    seen_filters: Mapping[str, Mapping[str, object]],
    conflicts: list[str],
) -> _ActPlan:
    kind = act.kind
    if not is_known_act_kind(kind):
        conflicts.append(f"act.unknown_kind:{kind}")
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key="act.rejected",
                    act_id=act.act_id,
                    status="rejected",
                    reason_code="act.unknown_kind",
                ),
            )
        )
    if kind == "resolve_pending":
        if context.pending_action is None:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key="pending.resolved",
                        act_id=act.act_id,
                        status="rejected",
                        reason_code="pending.action_not_found",
                    ),
                )
            )
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=EFFECT_PENDING_RESOLVED,
                    act_id=act.act_id,
                    status="applied",
                    detail={
                        "action_id": context.pending_action.action_id,
                        "kind": context.pending_action.kind,
                    },
                ),
            ),
            refresh_required=True,
        )
    if kind == "create_radar":
        if context.verified_profile_id is not None:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=EFFECT_RADAR_CREATED,
                        act_id=act.act_id,
                        status="rejected",
                        reason_code="radar.already_bound",
                    ),
                ),
                refresh_required=False,
            )
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=EFFECT_RADAR_CREATED,
                    act_id=act.act_id,
                    status="applied",
                    object_type="radar",
                ),
            ),
            refresh_required=True,
        )
    if kind == "set_filter":
        key = str(act.payload.get("key") or "")
        value = act.payload.get("value")
        if not key or value is None:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=EFFECT_FILTER_SET,
                        act_id=act.act_id,
                        status="rejected",
                        reason_code="filter.missing_value",
                    ),
                )
            )
        existing = seen_filters.get(key)
        if existing is None:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=EFFECT_FILTER_SET,
                        act_id=act.act_id,
                        status="applied",
                        object_type="radar",
                        detail={"key": key, "value": value},
                    ),
                ),
                refresh_required=True,
                applied_filters={key: {"value": value}},
            )
        if existing.get("value") == value:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=EFFECT_FILTER_SET,
                        act_id=act.act_id,
                        status="applied",
                        object_type="radar",
                        detail={"key": key, "value": value},
                    ),
                ),
                # Same value: no material change, but refresh reflects intent.
                refresh_required=False,
            )
        # Changing an existing hard filter is material (FR-013).
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=EFFECT_FILTER_SET,
                    act_id=act.act_id,
                    status="pending",
                    object_type="radar",
                    detail={"key": key, "value": value},
                    reason_code="filter.changes_existing_hard_filter",
                ),
            ),
            confirmation_required=True,
        )
    if kind == "clear_filter":
        key = str(act.payload.get("key") or "")
        if not key:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=EFFECT_FILTER_CLEARED,
                        act_id=act.act_id,
                        status="rejected",
                        reason_code="filter.missing_key",
                    ),
                )
            )
        if key not in seen_filters:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=EFFECT_FILTER_CLEARED,
                        act_id=act.act_id,
                        status="rejected",
                        reason_code="filter.not_active",
                    ),
                )
            )
        # Removing an active hard filter is material (FR-013).
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=EFFECT_FILTER_CLEARED,
                    act_id=act.act_id,
                    status="pending",
                    object_type="radar",
                    detail={"key": key},
                    reason_code="filter.removes_hard_filter",
                ),
            ),
            confirmation_required=True,
        )
    if kind in {"express_preference", "revise_preference", "withdraw_preference"}:
        subject_key = str(act.payload.get("subject_key") or "")
        if not subject_key:
            return _ActPlan(
                effects=(
                    TurnEffect(
                        effect_key=f"preference.{kind}",
                        act_id=act.act_id,
                        status="rejected",
                        reason_code="preference.missing_subject_key",
                    ),
                )
            )
        applied_key = (
            EFFECT_PREFERENCE_REMEMBERED
            if kind == "express_preference"
            else EFFECT_PREFERENCE_REVISED
            if kind == "revise_preference"
            else EFFECT_PREFERENCE_WITHDRAWN
        )
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=applied_key,
                    act_id=act.act_id,
                    status="applied",
                    object_type="preference",
                    detail={"subject_key": subject_key},
                ),
            ),
            refresh_required=True,
        )
    if kind == "record_feedback":
        listing_id = act.payload.get("listing_id")
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=EFFECT_FEEDBACK_RECORDED,
                    act_id=act.act_id,
                    status="applied",
                    object_type="listing",
                    object_id=str(listing_id) if listing_id else None,
                ),
            ),
            # Feedback may adjust soft preference weight; a refresh reflects it.
            refresh_required=True,
        )
    if kind == "query":
        return _ActPlan(
            effects=(
                TurnEffect(
                    effect_key=EFFECT_QUERY,
                    act_id=act.act_id,
                    status="applied",
                ),
            )
        )
    # Defensive: unknown kinds already rejected above.
    return _ActPlan()