"""Deterministic planning policy of the conversational copilot."""

from __future__ import annotations

from uuid import uuid4

import pytest

from umbral.application.conversation.contracts import (
    ConversationAct,
    ConversationContradiction,
    ConversationTurnContext,
    PendingAction,
    TurnInterpretation,
)
from umbral.application.conversation.policy import plan_turn


def _context(**overrides: object) -> ConversationTurnContext:
    values: dict[str, object] = {
        "user_id": uuid4(),
        "session_id": uuid4(),
        "verified_profile_id": uuid4(),
    }
    values.update(overrides)
    return ConversationTurnContext(
        user_id=values["user_id"],  # type: ignore[arg-type]
        session_id=values["session_id"],  # type: ignore[arg-type]
        verified_profile_id=values.get("verified_profile_id"),  # type: ignore[arg-type]
        pending_action=values.get("pending_action"),  # type: ignore[arg-type]
        answered_slots=tuple(values.get("answered_slots") or ()),  # type: ignore[arg-type]
        radar_filters=values.get("radar_filters") or {},  # type: ignore[arg-type]
    )


def _act(kind: str, *, act_id: str = "a1", **payload: object) -> ConversationAct:
    return ConversationAct(
        act_id=act_id,
        kind=kind,
        payload=payload,
        confidence=0.9,
    )


def test_first_intent_creates_a_partial_radar_and_requests_refresh() -> None:
    ctx = _context(verified_profile_id=None, radar_filters={})
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(
                _act("create_radar", name="Mi búsqueda"),
                _act("express_preference", subject_key="luminosidad"),
            )
        ),
        context=ctx,
    )

    assert plan.routing.refresh_required is True
    assert plan.routing.confirmation_required is False
    assert [effect.status for effect in plan.effects] == ["applied", "applied"]
    assert [effect.effect_key for effect in plan.effects] == [
        "radar.created",
        "preference.remembered",
    ]


def test_new_hard_filter_on_open_radar_applies_without_confirmation() -> None:
    ctx = _context(radar_filters={})
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("set_filter", key="budget_max", value=900),)
        ),
        context=ctx,
    )

    assert plan.routing.refresh_required is True
    assert plan.routing.confirmation_required is False
    assert plan.effects[0].status == "applied"


def test_changing_an_existing_hard_filter_requires_confirmation() -> None:
    ctx = _context(radar_filters={"budget_max": {"value": 800}})
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("set_filter", key="budget_max", value=1000),)
        ),
        context=ctx,
    )

    assert plan.routing.confirmation_required is True
    assert plan.effects[0].status == "pending"
    assert plan.effects[0].reason_code == "filter.changes_existing_hard_filter"


def test_same_hard_filter_value_is_not_material() -> None:
    ctx = _context(radar_filters={"budget_max": {"value": 800}})
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("set_filter", key="budget_max", value=800),)
        ),
        context=ctx,
    )

    assert plan.routing.confirmation_required is False
    assert plan.effects[0].status == "applied"


def test_clearing_an_active_filter_requires_confirmation() -> None:
    ctx = _context(radar_filters={"zones": {"zones": ["palermo"]}})
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("clear_filter", key="zones"),)
        ),
        context=ctx,
    )

    assert plan.routing.confirmation_required is True
    assert plan.effects[0].reason_code == "filter.removes_hard_filter"


def test_resolve_pending_takes_precedence_over_layout_acts() -> None:
    pending = PendingAction(
        kind="profile",
        action_id="proposal-1",
        diff={"budget_max": 1200},
    )
    ctx = _context(pending_action=pending)
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(
                _act("resolve_pending", decision="approve"),
                _act("express_preference", subject_key="balcon"),
            )
        ),
        context=ctx,
    )

    assert plan.effects[0].effect_key == "pending.resolved"
    assert plan.effects[0].status == "applied"
    assert plan.effects[0].detail["action_id"] == "proposal-1"
    assert plan.routing.refresh_required is True


def test_resolve_without_pending_action_is_rejected_not_applied() -> None:
    ctx = _context(pending_action=None)
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("resolve_pending", decision="approve"),)
        ),
        context=ctx,
    )

    assert plan.effects[0].status == "rejected"
    assert plan.effects[0].reason_code == "pending.action_not_found"
    assert plan.routing.confirmation_required is False


def test_query_has_no_refresh_and_does_not_mutate() -> None:
    ctx = _context()
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("query"),),
        ),
        context=ctx,
    )

    assert plan.routing.refresh_required is False
    assert plan.routing.confirmation_required is False
    assert plan.effects[0].effect_key == "query"


def test_create_radar_when_already_bound_is_rejected() -> None:
    ctx = _context(verified_profile_id=uuid4())
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("create_radar", name="Otra"),),
        ),
        context=ctx,
    )

    assert plan.effects[0].status == "rejected"
    assert plan.effects[0].reason_code == "radar.already_bound"


def test_unknown_or_contradictory_acts_raise_without_mutation() -> None:
    ctx = _context()
    with pytest.raises(ConversationContradiction):
        plan_turn(
            interpretation=TurnInterpretation(
                acts=(ConversationAct(act_id="x", kind="mutate_database"),),
            ),
            context=ctx,
        )


def test_withdraw_preference_is_reversible_and_refreshes() -> None:
    ctx = _context()
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("withdraw_preference", subject_key="balcon"),),
        ),
        context=ctx,
    )

    assert plan.effects[0].effect_key == "preference.withdrawn"
    assert plan.effects[0].status == "applied"
    assert plan.routing.refresh_required is True


def test_record_feedback_orients_soft_weight_without_hard_effect() -> None:
    ctx = _context()
    plan = plan_turn(
        interpretation=TurnInterpretation(
            acts=(
                _act(
                    "record_feedback",
                    listing_id=str(uuid4()),
                    decision="like",
                ),
            ),
        ),
        context=ctx,
    )

    assert plan.effects[0].effect_key == "feedback.recorded"
    assert plan.effects[0].status == "applied"
    assert plan.routing.refresh_required is True


def test_now_is_not_used_by_the_pure_planner() -> None:
    """The planner stays deterministic: no clock, no I/O, no counters."""
    ctx_a = _context(radar_filters={})
    ctx_b = _context(radar_filters={})
    first = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("set_filter", key="min_rooms", value=2),)
        ),
        context=ctx_a,
    )
    second = plan_turn(
        interpretation=TurnInterpretation(
            acts=(_act("set_filter", key="min_rooms", value=2),)
        ),
        context=ctx_b,
    )

    assert first.effects == second.effects
    assert first.routing == second.routing