"""Agent state unit tests (US2, FR-005)."""

from __future__ import annotations

import json
from uuid import UUID

from umbral.agent.state import (
    STATE_SCHEMA_VERSION,
    AgentState,
    as_serializable,
    build_initial_state,
)


def _state() -> AgentState:
    return build_initial_state(
        schema_version=STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )


def test_initial_state_has_all_v1_fields() -> None:
    state = _state()
    assert state["schema_version"] == STATE_SCHEMA_VERSION
    assert state["messages"] == [{"role": "user", "content": "hola"}]
    assert state["intent"] is None
    assert state["pending_action"] is None
    assert state["tool_results"] == []
    assert state["errors"] == []
    assert state["context"]["effects_applied"] == {}
    assert state["context"]["token_usage"] == {"input": 0, "output": 0, "total": 0}


def test_as_serializable_is_json_round_trippable() -> None:
    state = _state()
    state["context"]["effects_applied"] = {"user_message": str(UUID(int=9))}
    data = json.loads(json.dumps(as_serializable(state)))
    assert data["context"]["effects_applied"] == {"user_message": str(UUID(int=9))}
    assert data["messages"] == [{"role": "user", "content": "hola"}]


def test_pending_action_is_modeled_but_null_in_v1() -> None:
    state = _state()
    assert "pending_action" in state
    assert state["pending_action"] is None
