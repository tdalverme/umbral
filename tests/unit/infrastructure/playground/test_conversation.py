from __future__ import annotations

from umbral.application.playground.contracts import ConversationRequest
from umbral.infrastructure.playground.conversation import (
    build_local_conversation_runner,
)


def test_each_fake_run_gets_a_fresh_profile_copy() -> None:
    runner = build_local_conversation_runner()
    request = ConversationRequest(
        fixture_id="demo",
        turns=("bajá el presupuesto a 1000",),
        model_mode="fake",
    )

    first = runner.run(request)
    second = runner.run(request)

    assert first.state_after == second.state_after
    assert first.run_id != second.run_id


def test_fake_run_records_profile_proposal_tool_and_state_change() -> None:
    runner = build_local_conversation_runner()
    request = ConversationRequest(
        fixture_id="demo",
        turns=("bajá el presupuesto a 1000", "confirmo"),
        model_mode="fake",
    )

    result = runner.run(request)

    assert result.error is None
    assert result.turns[0]["tool_calls"] == [
        {"tool": "propose_search_profile_update", "status": "ok"}
    ]
    assert result.turns[1]["tool_calls"] == [
        {"tool": "apply_search_profile_update", "status": "ok"}
    ]
    assert result.state_after["budget_max"] == 1000
