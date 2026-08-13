# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""propose_search_preference_update tool tests (014-soft-preferences-chat)."""

from __future__ import annotations

from uuid import UUID

from tests.support.tools import build_executor, call_tool, payload

USER_PROFILE_ID = UUID(int=5)


def test_preference_tool_creates_pending_proposal_from_natural_phrase() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "luminoso"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["state"] == "pending"
    assert data["proposal_id"]
    assert data["diff"]["concept_key"] == "luminosidad"
    assert data["diff"]["polarity"] == "positive"
    assert data["impact"]["will_recompute"] is True
    assert data["impact"]["contradicts"] is False
    assert services.feedback.preference_calls == [
        {
            "profile_id": str(USER_PROFILE_ID),
            "concept_key": "luminosidad",
            "polarity": "positive",
            "value": None,
            "correlation_id": str(UUID(int=9)),
        }
    ]


def test_preference_tool_keeps_categorical_value() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "cocina separada"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["diff"]["concept_key"] == "tipo_cocina"
    assert data["diff"]["concept_value"] == "separada"


def test_preference_tool_rejects_unknown_phrase_with_actionable_code() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "cerca del subte"},
    )
    assert result.status == "error"
    assert result.error_code == "preference.unknown_concept"


def test_preference_tool_requires_non_empty_phrase() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "   "},
    )
    assert result.status == "error"
    assert result.error_code == "tool.args_invalid"


def test_preference_removal_tool_creates_pending_removal_proposal() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_removal",
        {"preference": "luminosidad"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["state"] == "pending"
    assert data["diff"]["concept_key"] == "luminosidad"
    assert data["diff"]["operation"] == "remove"
    assert data["impact"]["operation"] == "remove"
    assert services.feedback.preference_calls[-1]["operation"] == "remove"


def test_preference_list_returns_active_facts() -> None:
    executor, _ = build_executor()
    result = call_tool(executor, "list_search_preferences", {})
    assert result.status == "ok"
    assert payload(result)["preferences"] == []


def test_learning_confirmation_tool_creates_pending_decision() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_learning_confirmation",
        {"learning_proposal_id": str(UUID(int=95))},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["state"] == "pending"
    assert data["diff"]["concept_key"] == "luminosidad"
    assert data["diff"]["operation"] == "learning"
    assert data["impact"]["source"] == "feedback"


def test_learning_confirmation_tool_requires_valid_uuid() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_learning_confirmation",
        {"learning_proposal_id": "no-uuid"},
    )
    assert result.status == "error"
    assert result.error_code == "tool.args_invalid"
