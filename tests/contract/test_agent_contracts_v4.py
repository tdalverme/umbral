"""Conformance of the conversational agent v4 contract documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_contract(relative_path: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    )


def test_interpretation_v4_accepts_ordered_multi_act_payload() -> None:
    """Removing ordered acts or a supported act kind must reject this turn."""
    schema = _load_contract("contracts/agent/v4/interpretation-schema-v4.json")
    payload = {
        "contract_version": "4",
        "interpretation_version": "conversation-interpretation-v4",
        "acts": [
            {
                "act_id": "a1",
                "kind": "resolve_pending",
                "target": {},
                "payload": {"decision": "approve"},
                "confidence": 0.99,
            },
            {
                "act_id": "a2",
                "kind": "express_preference",
                "target": {},
                "payload": {"subject_key": "balcon", "text": "quiero balcon"},
                "confidence": 0.95,
            },
        ],
        "ambiguity": None,
    }

    jsonschema.validate(payload, schema)


def test_interpretation_v4_rejects_unknown_act_kind() -> None:
    """Widening the model's action vocabulary must be an explicit contract change."""
    schema = _load_contract("contracts/agent/v4/interpretation-schema-v4.json")
    payload = {
        "contract_version": "4",
        "interpretation_version": "conversation-interpretation-v4",
        "acts": [
            {
                "act_id": "a1",
                "kind": "mutate_database",
                "target": {},
                "payload": {},
                "confidence": 1.0,
            }
        ],
        "ambiguity": None,
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_state_v4_declares_an_optional_search_profile_context() -> None:
    """Making profile binding mandatory would block first-turn radar creation."""
    state = _load_contract("contracts/agent/v4/state-schema-v4.json")

    assert state["contract_version"] == "4"
    assert state["registry_version"] == "agent-state-schema-v4"
    context = next(field for field in state["fields"] if field["name"] == "context")
    assert context["search_profile_id"] == {"kind": "nullable_uuid", "required": True}


def test_reply_and_graph_v4_publish_the_deterministic_turn_boundaries() -> None:
    """Removing planning, safe application, or persistence would bypass policy."""
    reply = _load_contract("contracts/agent/v4/reply-schema-v4.json")
    topology = _load_contract("contracts/agent/v4/graph-topology-v4.json")

    assert reply["contract_version"] == "4"
    assert reply["registry_version"] == "agent-reply-schema-v4"
    assert reply["fields"]["effects"]["item"]["status"]["enum"] == [
        "applied",
        "pending",
        "remembered",
        "rejected",
    ]
    assert {node["name"] for node in topology["nodes"]} == {
        "load_context",
        "interpret_turn",
        "plan_effects",
        "apply_safe_effects",
        "require_confirmation",
        "resolve_pending",
        "schedule_refresh",
        "compose_reply",
        "persist_reply",
    }
