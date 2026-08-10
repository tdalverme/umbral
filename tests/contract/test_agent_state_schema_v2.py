"""State schema v2 conformance (FR-004/FR-005, T015)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from umbral.agent.state import (
    TOOLS_STATE_SCHEMA_VERSION,
    as_serializable,
    build_initial_state,
)

ROOT = Path(__file__).resolve().parents[2]
STATE_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v2" / "state-schema-v2.json").read_text(
        encoding="utf-8"
    )
)


def test_state_v2_contract_declares_tool_calls_and_results() -> None:
    assert STATE_CONTRACT["contract_version"] == "2"
    assert STATE_CONTRACT["registry_version"] == "agent-state-schema-v2"
    assert STATE_CONTRACT["schema_version"] == TOOLS_STATE_SCHEMA_VERSION
    assert STATE_CONTRACT["serializable"] is True
    names = {field["name"] for field in STATE_CONTRACT["fields"]}
    assert names == {
        "schema_version",
        "messages",
        "context",
        "intent",
        "pending_action",
        "tool_calls",
        "tool_results",
        "errors",
    }


def test_initial_state_v2_has_empty_tool_calls() -> None:
    state = build_initial_state(
        schema_version=TOOLS_STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    assert state["schema_version"] == TOOLS_STATE_SCHEMA_VERSION
    assert state["tool_calls"] == []
    assert state["tool_results"] == []

    serialized = as_serializable(state)
    round_tripped = json.loads(json.dumps(serialized))
    assert round_tripped["tool_calls"] == []
    assert round_tripped["tool_results"] == []


def test_v2_state_with_tool_calls_is_json_safe() -> None:
    state = build_initial_state(
        schema_version=TOOLS_STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    state["tool_calls"] = [{"tool": "find_matches", "args": {"page": 1}}]
    state["tool_results"] = [
        {"tool": "find_matches", "status": "ok", "result": {"total": 1}}
    ]
    data = json.loads(json.dumps(as_serializable(state)))
    assert data["tool_calls"][0]["tool"] == "find_matches"
    assert data["tool_results"][0]["status"] == "ok"
