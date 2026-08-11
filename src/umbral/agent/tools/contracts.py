"""Pure values for the explicit, permissioned tool surface (H4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

ToolRunStatus = Literal["ok", "error"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A pending tool invocation produced by the orchestrator."""

    tool: str
    args: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A redacted tool outcome; never carries forbidden keys or raw output."""

    tool: str
    status: ToolRunStatus
    result: Mapping[str, object] | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ToolRunContext:
    """Identity and scope a tool may operate within; nothing outside it."""

    user_id: UUID
    session_id: UUID
    search_profile_id: UUID
    run_id: UUID
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One declared tool from the machine-checkable tool contract."""

    name: str
    description: str
    mutating: bool
    requires_confirmation: bool
    idempotent: bool
    timeout_seconds: float
    input_schema: Mapping[str, object]
    output_schema: Mapping[str, object]
    output_limits: Mapping[str, object]


class ToolError(Exception):
    """Base class for sanitized tool failures."""

    code = "tool.error"

    def __init__(self, code: str | None = None, message: str | None = None) -> None:
        self.code = code or type(self).code
        super().__init__(message or self.code)


class ToolNotFound(ToolError):
    """The requested tool is not in the published contract."""

    code = "tool.not_found"


class ToolArgsInvalid(ToolError):
    """Arguments do not satisfy the tool input schema; 0 effects."""

    code = "tool.args_invalid"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(message=detail)


class ToolScopeViolation(ToolError):
    """The invocation target is outside the session's search profile."""

    code = "tool.scope_violation"


class ToolConfirmationRequired(ToolError):
    """A mutating tool that requires confirmation was invoked without it."""

    code = "tool.confirmation_required"


class ToolIdempotencyConflict(ToolError):
    """A mutating tool missing its idempotency key or replaying a different key."""

    code = "tool.idempotency_conflict"


class ToolTimeout(ToolError):
    """The tool exceeded its allowed execution time."""

    code = "tool.timeout"


def parse_tool_contract(data: Mapping[str, object]) -> list[ToolSpec]:
    """Parse and validate the machine-checkable tool contract.

    Accepts v1 (plain ``{field: kind}`` input schemas) and v2 (enriched
    ``{field: {kind, description?, enum?}}``). Raises ``ToolContractInvalid``
    for structural violations; unknown tools are rejected at runtime by the
    registry, never silently accepted.
    """

    if data.get("registry_version") not in {
        "agent-tool-contract-v1",
        "agent-tool-contract-v2",
    }:
        raise ToolContractInvalid("registry_version")
    if data.get("contract_version") not in {"1", "2"}:
        raise ToolContractInvalid("contract_version")
    raw_tools = data.get("tools")
    if not isinstance(raw_tools, list):
        raise ToolContractInvalid("tools")
    tools: list[ToolSpec] = []
    for raw in raw_tools:
        if not isinstance(raw, Mapping):
            raise ToolContractInvalid("tool")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ToolContractInvalid("tool.name")
        if any(existing.name == name for existing in tools):
            raise ToolContractInvalid("tool.duplicate")
        tools.append(
            ToolSpec(
                name=name,
                description=_string(raw, "description"),
                mutating=_bool(raw, "mutating"),
                requires_confirmation=_bool(raw, "requires_confirmation"),
                idempotent=_bool(raw, "idempotent"),
                timeout_seconds=_number(raw, "timeout_seconds"),
                input_schema=_mapping(raw, "input_schema"),
                output_schema=_mapping(raw, "output_schema"),
                output_limits=_mapping(raw, "output_limits"),
            )
        )
    return tools


class ToolContractInvalid(ValueError):
    """A tool contract file failed structural validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"tool_contract_invalid: {reason}")


def _string(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ToolContractInvalid(f"tool.{key}")
    return value


def _bool(raw: Mapping[str, object], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ToolContractInvalid(f"tool.{key}")
    return value


def _number(raw: Mapping[str, object], key: str) -> float:
    value = raw.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ToolContractInvalid(f"tool.{key}")
    return float(value)


def _mapping(raw: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise ToolContractInvalid(f"tool.{key}")
    return value
