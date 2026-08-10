"""Intent-to-tools policy unit tests (UM-H4-017, T016)."""

from __future__ import annotations

from umbral.agent.intent.policy import validate_tool_calls


def test_allowed_calls_pass() -> None:
    violations = validate_tool_calls(
        allowed_tools=["find_matches", "explain_match"],
        tool_calls=[{"tool": "find_matches", "args": {}}],
    )
    assert violations == ()


def test_tool_outside_policy_is_rejected() -> None:
    violations = validate_tool_calls(
        allowed_tools=["find_matches"],
        tool_calls=[
            {"tool": "find_matches", "args": {}},
            {"tool": "apply_search_profile_update", "args": {}},
        ],
    )
    assert len(violations) == 1
    assert violations[0].tool == "apply_search_profile_update"
    assert violations[0].code == "agent.tool_not_allowed"


def test_out_of_scope_intent_allows_no_calls() -> None:
    violations = validate_tool_calls(
        allowed_tools=[],
        tool_calls=[{"tool": "get_search_profile", "args": {}}],
    )
    assert len(violations) == 1


def test_malformed_call_is_rejected() -> None:
    violations = validate_tool_calls(
        allowed_tools=["find_matches"], tool_calls=[{"args": {}}]
    )
    assert len(violations) == 1
