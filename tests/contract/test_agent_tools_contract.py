"""Tool contract v1 conformance (FR-001..FR-003, T007)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.agent.tools.contracts import ToolContractInvalid, parse_tool_contract
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract

ROOT = Path(__file__).resolve().parents[2]
EVENTS_REGISTRY = json.loads(
    (ROOT / "contracts" / "events" / "v1" / "events-registry.json").read_text(
        encoding="utf-8"
    )
)

EXPECTED_TOOLS_V1 = {
    "get_search_profile",
    "propose_search_profile_update",
    "apply_search_profile_update",
    "find_matches",
    "explain_match",
    "compare_listings",
    "record_feedback",
    "search_urban_context",
}

EXPECTED_TOOLS_V2 = EXPECTED_TOOLS_V1 | {
    "get_listing_detail",
    "propose_search_preference_update",
    "propose_search_preference_removal",
    "propose_learning_confirmation",
    "list_search_preferences",
}


def test_tool_contract_v2_exposes_the_13_published_tools() -> None:
    tools = load_tool_contract()
    assert {tool.name for tool in tools} == EXPECTED_TOOLS_V2


def test_tool_contract_flags_are_correct() -> None:
    tools = {tool.name: tool for tool in load_tool_contract()}
    assert tools["apply_search_profile_update"].requires_confirmation is True
    assert tools["apply_search_profile_update"].mutating is True
    assert tools["apply_search_profile_update"].idempotent is True
    assert tools["propose_search_profile_update"].mutating is True
    assert tools["propose_search_profile_update"].idempotent is True
    assert tools["propose_search_preference_update"].mutating is True
    assert tools["propose_search_preference_update"].idempotent is True
    assert tools["propose_search_preference_update"].requires_confirmation is False
    assert "preference" in tools["propose_search_preference_update"].input_schema
    assert tools["propose_search_preference_removal"].mutating is True
    assert tools["propose_search_preference_removal"].idempotent is True
    assert "preference" in tools["propose_search_preference_removal"].input_schema
    assert tools["propose_learning_confirmation"].mutating is True
    assert tools["propose_learning_confirmation"].idempotent is True
    assert "learning_proposal_id" in tools["propose_learning_confirmation"].input_schema
    assert tools["list_search_preferences"].mutating is False
    assert tools["list_search_preferences"].input_schema == {}
    assert tools["find_matches"].mutating is False
    assert tools["find_matches"].requires_confirmation is False
    assert tools["record_feedback"].mutating is True
    assert tools["record_feedback"].idempotent is True
    assert tools["search_urban_context"].mutating is False


def test_tool_contract_v2_enriches_record_feedback_args() -> None:
    tools = {tool.name: tool for tool in load_tool_contract()}
    decision = tools["record_feedback"].input_schema["decision"]
    assert isinstance(decision, dict)
    assert decision["kind"] == "string"
    assert decision["enum"] == ["like", "dislike"]
    assert "idempotency_key" in tools["record_feedback"].input_schema


def test_tool_contract_v2_record_feedback_exposes_concept_feedback() -> None:
    tools = {tool.name: tool for tool in load_tool_contract()}
    concept_feedback = tools["record_feedback"].input_schema["concept_feedback"]
    assert isinstance(concept_feedback, dict)
    assert concept_feedback["kind"] == "array"
    assert concept_feedback["max_items"] == 5
    item = concept_feedback["item"]
    assert item["polarity"]["enum"] == ["positive", "negative"]
    assert item["strength"]["enum"] == ["low", "medium", "strong"]
    assert item["confidence"]["kind"] == "number"


def test_tool_contract_v1_still_parses() -> None:
    v1 = json.loads(
        (ROOT / "contracts" / "agent" / "tools" / "tool-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    tools = parse_tool_contract(v1)
    assert {tool.name for tool in tools} == EXPECTED_TOOLS_V1


def test_tool_contract_redaction_reuses_events_forbidden_keys() -> None:
    forbidden = set(EVENTS_REGISTRY["forbidden_keys"])
    for tool in load_tool_contract():
        limits = tool.output_limits
        tool_keys = limits.get("forbidden_keys", [])
        assert isinstance(tool_keys, list)
        assert set(tool_keys) <= forbidden


def test_tool_contract_rejects_duplicate_names() -> None:
    data = {
        "registry_version": "agent-tool-contract-v1",
        "contract_version": "1",
        "tools": [
            {
                "name": "find_matches",
                "description": "x",
                "mutating": False,
                "requires_confirmation": False,
                "idempotent": False,
                "timeout_seconds": 10,
                "input_schema": {},
                "output_schema": {},
                "output_limits": {},
            },
            {
                "name": "find_matches",
                "description": "x",
                "mutating": False,
                "requires_confirmation": False,
                "idempotent": False,
                "timeout_seconds": 10,
                "input_schema": {},
                "output_schema": {},
                "output_limits": {},
            },
        ],
    }
    try:
        parse_tool_contract(data)
    except ToolContractInvalid:
        return
    raise AssertionError("duplicate tool names must be rejected")
