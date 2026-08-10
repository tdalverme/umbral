"""State schema v3 conformance (FR-001/FR-005, T017)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from umbral.agent.state import (
    CHAT_STATE_SCHEMA_VERSION,
    as_serializable,
    build_initial_state,
)

ROOT = Path(__file__).resolve().parents[2]
STATE_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v3" / "state-schema-v3.json").read_text(
        encoding="utf-8"
    )
)


def test_state_v3_contract_declares_intent_and_clarification() -> None:
    assert STATE_CONTRACT["contract_version"] == "3"
    assert STATE_CONTRACT["registry_version"] == "agent-state-schema-v3"
    assert STATE_CONTRACT["schema_version"] == CHAT_STATE_SCHEMA_VERSION
    names = {field["name"] for field in STATE_CONTRACT["fields"]}
    assert names == {
        "schema_version",
        "messages",
        "context",
        "intent",
        "clarification",
        "pending_action",
        "tool_calls",
        "tool_results",
        "errors",
    }


def test_initial_state_v3_has_empty_intent_and_clarification() -> None:
    state = build_initial_state(
        schema_version=CHAT_STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    assert state["schema_version"] == CHAT_STATE_SCHEMA_VERSION
    assert state["intent"] is None
    assert state["clarification"] is None
    serialized = json.loads(json.dumps(as_serializable(state)))
    assert serialized["clarification"] is None


def test_v3_state_with_clarification_is_json_safe() -> None:
    state = build_initial_state(
        schema_version=CHAT_STATE_SCHEMA_VERSION,
        run_id=str(UUID(int=1)),
        session_id=str(UUID(int=2)),
        user_id=str(UUID(int=3)),
        correlation_id=str(UUID(int=4)),
        user_message_text="hola",
    )
    state["clarification"] = {"pending_params": ["budget"], "rounds": 1}
    state["pending_action"] = {"kind": "proposal", "proposal_id": "p1"}
    data = json.loads(json.dumps(as_serializable(state)))
    assert data["clarification"]["pending_params"] == ["budget"]
    assert data["pending_action"]["proposal_id"] == "p1"
