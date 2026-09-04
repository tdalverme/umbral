"""Local playground runner over the single semantic graph."""

from __future__ import annotations

from umbral.application.playground.contracts import ConversationRequest
from umbral.infrastructure.playground.conversation import (
    build_local_conversation_runner,
)


def test_playground_budget_turn_interrupts_and_approves() -> None:
    runner = build_local_conversation_runner()
    fixture_id = runner.fixtures.items[0].fixture_id

    trace = runner.run(
        ConversationRequest(
            fixture_id=fixture_id,
            turns=("quiero presupuesto 900", "confirmo"),
            model_mode="fake",
        )
    )

    assert trace.error is None
    assert [turn["status"] for turn in trace.turns] == ["interrupted", "completed"]
    assert trace.turns[0]["interrupt"] is not None
    assert trace.state_after.get("budget_max") == 900.0


def test_playground_unknown_turn_answers_without_effects() -> None:
    runner = build_local_conversation_runner()
    fixture_id = runner.fixtures.items[0].fixture_id

    trace = runner.run(
        ConversationRequest(
            fixture_id=fixture_id,
            turns=("mostrame mis matches",),
            model_mode="fake",
        )
    )

    assert trace.error is None
    assert trace.turns[0]["status"] == "completed"
    assert trace.turns[0]["reply"] is not None
