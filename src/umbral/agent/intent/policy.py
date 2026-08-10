"""Deterministic intent-to-tools policy enforcement (UM-H4-017, R-02)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolPolicyViolation:
    """A generated tool call outside the compiled intent's allowed tools."""

    tool: str
    code: str = "agent.tool_not_allowed"


def validate_tool_calls(
    *, allowed_tools: Sequence[str], tool_calls: Sequence[Mapping[str, object]]
) -> tuple[ToolPolicyViolation, ...]:
    """Return the policy violations of the generated calls, or an empty tuple.

    Every ``tool_calls`` entry must reference a tool in ``allowed_tools``;
    a violation means the call is rejected before execution with 0 effects.
    """
    allowed = frozenset(allowed_tools)
    violations: list[ToolPolicyViolation] = []
    for call in tool_calls:
        tool = call.get("tool")
        if not isinstance(tool, str) or tool not in allowed:
            violations.append(ToolPolicyViolation(tool=str(tool)))
    return tuple(violations)
