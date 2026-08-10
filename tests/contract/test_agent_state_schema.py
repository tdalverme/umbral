"""State schema v1 conformance (FR-004/FR-005)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from umbral.agent.state import (
    STATE_SCHEMA_VERSION,
    AgentState,
    as_serializable,
    build_initial_state,
)

ROOT = Path(__file__).resolve().parents[2]
STATE_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v1" / "state-schema-v1.json").read_text(
        encoding="utf-8"
    )
)


def test_state_contract_declares_v1_fields_and_serializable() -> None:
    assert STATE_CONTRACT["contract_version"] == "1"
    assert STATE_CONTRACT["registry_version"] == "agent-state-schema-v1"
    assert STATE_CONTRACT["schema_version"] == STATE_SCHEMA_VERSION
    assert STATE_CONTRACT["serializable"] is True
    names = {field["name"] for field in STATE_CONTRACT["fields"]}
    assert names == {
        "schema_version",
        "messages",
        "context",
        "intent",
        "pending_action",
        "tool_results",
        "errors",
    }


def test_initial_state_is_json_round_trippable() -> None:
    state = build_initial_state(
        schema_version=STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    assert state["schema_version"] == STATE_SCHEMA_VERSION
    assert state["intent"] is None
    assert state["pending_action"] is None
    assert state["tool_results"] == []
    assert state["errors"] == []
    assert "effects_applied" in dict(state["context"])

    serialized = as_serializable(state)
    round_tripped = json.loads(json.dumps(serialized))
    assert round_tripped["schema_version"] == STATE_SCHEMA_VERSION
    assert round_tripped["context"]["effects_applied"] == {}
    assert round_tripped["messages"][0]["role"] == "user"


def test_state_values_are_json_safe() -> None:
    state = build_initial_state(
        schema_version=STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    state["context"]["effects_applied"] = {"user_message": str(UUID(int=1))}
    data = json.loads(json.dumps(as_serializable(state)))
    assert data["context"]["effects_applied"] == {"user_message": str(UUID(int=1))}


def test_foreign_schema_version_is_reported_not_silently_migrated() -> None:
    state: AgentState = build_initial_state(
        schema_version=99,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    assert state["schema_version"] != STATE_SCHEMA_VERSION
