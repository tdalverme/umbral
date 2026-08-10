# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""get_search_profile tool tests (FR-005/FR-006, T030)."""

from __future__ import annotations

from typing import Any, cast

from tests.support.tools import PROFILE_ID, build_executor, call_tool, payload

from umbral.agent.tools.contracts import ToolScopeViolation


def test_get_search_profile_returns_snapshot_criteria_and_state() -> None:
    executor, _ = build_executor()
    result = call_tool(executor, "get_search_profile")
    assert payload(result)["profile_id"] == str(PROFILE_ID)
    assert payload(result)["state"] == "active"
    snapshot = cast(Any, payload(result)["snapshot"])
    assert snapshot["budget_max"] == 150000
    assert snapshot["zones"] == ["palermo"]
    criteria = cast(Any, payload(result)["criteria"])
    assert criteria[0]["concept_key"] == "presupuesto"
    assert criteria[0]["matcher_type"] == "numeric_range"


def test_get_search_profile_denied_for_foreign_session() -> None:
    executor, _ = build_executor(deny_scope=True)
    result = call_tool(executor, "get_search_profile")
    assert result.status == "error"
    assert result.error_code == ToolScopeViolation.code
