"""Versioned agent state schemas v1/v2/v3 (UM-H4-002, FR-004/FR-005)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

STATE_SCHEMA_VERSION = 1
TOOLS_STATE_SCHEMA_VERSION = 2
CHAT_STATE_SCHEMA_VERSION = 3


class AgentState(TypedDict, total=False):
    """Checkpointed execution state; every value is JSON-safe (FR-005)."""

    schema_version: int
    messages: list[dict[str, object]]
    context: dict[str, object]
    intent: object | None
    clarification: object | None
    pending_action: object | None
    tool_calls: list[dict[str, object]]
    tool_results: list[dict[str, object]]
    errors: list[dict[str, object]]


def build_initial_state(
    *,
    schema_version: int,
    run_id: str,
    session_id: str,
    user_id: str,
    correlation_id: str,
    user_message_text: str,
    search_profile_id: str | None = None,
    client_message_id: str | None = None,
    user_message_context: Mapping[str, object] | None = None,
) -> AgentState:
    """Build the initial state for a fresh graph run (v1, v2 or v3)."""
    context: dict[str, object] = {
        "run_id": run_id,
        "session_id": session_id,
        "user_id": user_id,
        "correlation_id": correlation_id,
        "user_message_text": user_message_text,
        "effects_applied": {},
        "token_usage": {"input": 0, "output": 0, "total": 0},
    }
    if search_profile_id is not None:
        context["search_profile_id"] = search_profile_id
    if client_message_id is not None:
        context["client_message_id"] = client_message_id
    if user_message_context is not None:
        context["user_message_context"] = dict(user_message_context)
    return AgentState(
        schema_version=schema_version,
        messages=[{"role": "user", "content": user_message_text}],
        context=context,
        intent=None,
        clarification=None,
        pending_action=None,
        tool_calls=[],
        tool_results=[],
        errors=[],
    )


def as_serializable(state: AgentState) -> dict[str, Any]:
    """Return the state as plain JSON-safe data, asserting the invariant."""
    data = dict(state)
    context = dict(state.get("context") or {})
    data["context"] = context
    data["messages"] = [dict(item) for item in state.get("messages") or []]
    data["tool_calls"] = [dict(item) for item in state.get("tool_calls") or []]
    data["tool_results"] = [dict(item) for item in state.get("tool_results") or []]
    data["errors"] = [dict(item) for item in state.get("errors") or []]
    return data
