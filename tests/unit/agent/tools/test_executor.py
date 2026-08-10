# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Common tool executor policy tests (FR-001..FR-004, T014)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from tests.support.agent import RecordingRunRecorder
from tests.support.tools import payload

from umbral.agent.tools.contracts import (
    ToolArgsInvalid,
    ToolConfirmationRequired,
    ToolIdempotencyConflict,
    ToolNotFound,
    ToolScopeViolation,
    ToolTimeout,
)
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.tools.ports import SessionScope
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
PROFILE_ID = UUID(int=5)
RUN_ID = UUID(int=10)
CORRELATION_ID = UUID(int=20)


class _ScopeReader:
    def __init__(self, scope: SessionScope | None) -> None:
        self.scope = scope

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        return self.scope


_DEFAULT_SCOPE = SessionScope(
    session_id=SESSION_ID, search_profile_id=PROFILE_ID, status="active"
)


def _make_executor(
    implementations=None,
    *,
    scope: SessionScope | None = _DEFAULT_SCOPE,
    timeout_seconds: float = 1.0,
) -> tuple[ToolExecutor, RecordingRunRecorder]:
    recorder = RecordingRunRecorder()
    executor = ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations=implementations or {},
        recorder=recorder,
        scope_reader=_ScopeReader(scope),
        timeout_seconds=timeout_seconds,
    )
    return executor, recorder


def _call(
    executor: ToolExecutor,
    name: str,
    args=None,
    *,
    confirmation: bool = False,
):
    return executor.execute(
        user_id=USER_ID,
        session_id=SESSION_ID,
        run_id=RUN_ID,
        correlation_id=CORRELATION_ID,
        name=name,
        args=args or {},
        confirmation=confirmation,
    )


def test_scope_violation_denied_when_session_unknown() -> None:
    executor, recorder = _make_executor(scope=None)
    result = _call(executor, "find_matches", {"page": 1, "limit": 5})
    assert result.status == "error"
    assert result.error_code == ToolScopeViolation.code
    assert recorder.nodes[-1].status == "failed"


def test_scope_violation_denied_when_session_not_active() -> None:
    scope = SessionScope(
        session_id=SESSION_ID, search_profile_id=PROFILE_ID, status="paused"
    )
    executor, _ = _make_executor(scope=scope)
    result = _call(executor, "find_matches", {"page": 1, "limit": 5})
    assert result.status == "error"
    assert result.error_code == ToolScopeViolation.code


def test_unknown_tool_rejected() -> None:
    executor, _ = _make_executor()
    result = _call(executor, "no_such_tool")
    assert result.status == "error"
    assert result.error_code == ToolNotFound.code


def test_args_out_of_schema_rejected_with_zero_effects() -> None:
    executor, recorder = _make_executor(
        {"find_matches": lambda _ctx, _args: {"items": []}}
    )
    result = _call(executor, "find_matches", {"page": "no-un-int", "limit": 5})
    assert result.status == "error"
    assert result.error_code == ToolArgsInvalid.code
    assert recorder.nodes[-1].status == "failed"


def test_confirmation_required_is_enforced() -> None:
    executor, _ = _make_executor(
        {"apply_search_profile_update": lambda _ctx, _args: {"ok": True}}
    )
    result = _call(
        executor,
        "apply_search_profile_update",
        {
            "proposal_id": str(UUID(int=1)),
            "confirmation": False,
            "idempotency_key": "k-1",
        },
    )
    assert result.status == "error"
    assert result.error_code == ToolConfirmationRequired.code


def test_confirmation_true_accepts_mutating_tool() -> None:
    executor, _ = _make_executor(
        {"apply_search_profile_update": lambda _ctx, _args: {"ok": True}}
    )
    result = _call(
        executor,
        "apply_search_profile_update",
        {
            "proposal_id": str(UUID(int=1)),
            "confirmation": True,
            "idempotency_key": "k-1",
        },
        confirmation=True,
    )
    assert result.status == "ok"


def test_idempotency_key_required_for_mutating_tools() -> None:
    executor, _ = _make_executor(
        {
            "apply_search_profile_update": lambda _ctx, _args: {"ok": True},
            "record_feedback": lambda _ctx, _args: {"noop": False},
        }
    )
    result = _call(
        executor,
        "apply_search_profile_update",
        {
            "proposal_id": str(UUID(int=1)),
            "confirmation": True,
            "idempotency_key": "",
        },
        confirmation=True,
    )
    assert result.status == "error"
    assert result.error_code == ToolIdempotencyConflict.code


def test_successful_tool_is_redacted_and_recorded() -> None:
    def find_matches(_ctx, _args):
        return {
            "run_id": None,
            "items": [{"value": 100, "fragment": "x"}],
            "total": 1,
            "stale": True,
        }

    executor, recorder = _make_executor({"find_matches": find_matches})
    result = _call(executor, "find_matches", {"page": 1, "limit": 5})
    assert result.status == "ok"
    # forbidden_keys (value/fragment) are dropped by redaction (FR-003).
    items = cast(Any, payload(result)["items"])
    assert "value" not in items[0]
    assert "fragment" not in items[0]
    assert len(recorder.nodes) == 1
    assert recorder.nodes[0].node_kind == "tool"
    assert recorder.nodes[0].node_name == "find_matches"
    assert recorder.nodes[0].status == "completed"


def test_tool_timeout_marks_failure() -> None:
    import time

    def slow_tool(_ctx, _args):
        time.sleep(0.01)
        return {"ok": True}

    executor, recorder = _make_executor(
        {"find_matches": slow_tool}, timeout_seconds=0.001
    )
    result = _call(executor, "find_matches", {"page": 1, "limit": 5})
    assert result.status == "error"
    assert result.error_code == ToolTimeout.code
    assert recorder.nodes[-1].status == "failed"


def test_tool_failure_is_typed_and_recorded() -> None:
    def broken(_ctx, _args):
        raise ValueError("boom")

    executor, recorder = _make_executor({"find_matches": broken})
    result = _call(executor, "find_matches", {"page": 1, "limit": 5})
    assert result.status == "error"
    assert result.result is None
    assert recorder.nodes[-1].status == "failed"

