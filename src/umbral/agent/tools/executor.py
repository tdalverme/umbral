"""Common tool policy executor: scope, schema, confirmation, timeout, redaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.agent.tools.contracts import (
    ToolConfirmationRequired,
    ToolError,
    ToolIdempotencyConflict,
    ToolNotFound,
    ToolResult,
    ToolRunContext,
    ToolScopeViolation,
    ToolSpec,
    ToolTimeout,
)
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.contracts import NodeRun
from umbral.application.agent.ports import RunRecorder
from umbral.application.agent.tools.ports import SessionScope, SessionScopeReader

ToolImplementation = Callable[
    [ToolRunContext, Mapping[str, object]], Mapping[str, object]
]

_ACTIVE_STATUSES = {"active"}


class ToolExecutor:
    """Enforces the common contract for every tool invocation (FR-001..FR-004).

    Every call validates identity and search scope, input schema, confirmation
    and timeout policy, delegates to the declared implementation, redacts the
    output and records one tool run (``NodeRun`` with ``node_kind='tool'``).
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        implementations: Mapping[str, ToolImplementation],
        recorder: RunRecorder,
        scope_reader: SessionScopeReader,
        timeout_seconds: float = 10.0,
        output_max_items: int = 20,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.registry = registry
        self.implementations = implementations
        self.recorder = recorder
        self.scope_reader = scope_reader
        self.timeout_seconds = timeout_seconds
        self.output_max_items = output_max_items
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        run_id: UUID,
        correlation_id: UUID,
        name: str,
        args: Mapping[str, object],
        confirmation: bool = False,
    ) -> ToolResult:
        started_at = self.clock()
        error_code: str | None = None
        raw: Mapping[str, object] | None = None
        try:
            spec = self._resolve(name)
            self.registry.validate_args(spec, args)
            scope = self._read_scope(user_id, session_id)
            self._validate_confirmation(spec, confirmation)
            self._validate_idempotency(spec, args)
            implementation = self._implementation(name)
            raw = implementation(
                ToolRunContext(
                    user_id=user_id,
                    session_id=session_id,
                    search_profile_id=scope.search_profile_id,
                    run_id=run_id,
                    correlation_id=correlation_id,
                ),
                args,
            )
        except ToolError as exc:
            error_code = exc.code
        except Exception:  # noqa: BLE001 - unknown tool failure, typed at boundary
            error_code = ToolError().code
        finished_at = self.clock()
        if (
            error_code is None
            and _elapsed_ms(started_at, finished_at) > self.timeout_seconds * 1000
        ):
            error_code = ToolTimeout().code
        if error_code is not None:
            self._record_tool_run(
                run_id=run_id,
                correlation_id=correlation_id,
                node_name=name,
                started_at=started_at,
                finished_at=finished_at,
                error_code=error_code,
            )
            return ToolResult(tool=name, status="error", error_code=error_code)
        assert raw is not None
        redacted = self.registry.apply_redaction(self._resolve(name), raw)
        self._record_tool_run(
            run_id=run_id,
            correlation_id=correlation_id,
            node_name=name,
            started_at=started_at,
            finished_at=finished_at,
        )
        return ToolResult(tool=name, status="ok", result=redacted)

    def _resolve(self, name: str) -> ToolSpec:
        return self.registry.get(name)

    def _read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope:
        scope = self.scope_reader.read_scope(user_id, session_id)
        if scope is None or scope.search_profile_id is None:
            raise ToolScopeViolation()
        if scope.status not in _ACTIVE_STATUSES:
            raise ToolScopeViolation()
        return scope

    def _validate_confirmation(self, spec: ToolSpec, confirmation: bool) -> None:
        if spec.requires_confirmation and not confirmation:
            raise ToolConfirmationRequired()

    def _validate_idempotency(
        self, spec: ToolSpec, args: Mapping[str, object]
    ) -> None:
        if spec.mutating and "idempotency_key" in spec.input_schema:
            key = args.get("idempotency_key")
            if key is None or (isinstance(key, str) and not key.strip()):
                raise ToolIdempotencyConflict()

    def _implementation(self, name: str) -> ToolImplementation:
        implementation = self.implementations.get(name)
        if implementation is None:
            raise ToolNotFound()
        return implementation

    def _record_tool_run(
        self,
        *,
        run_id: UUID,
        correlation_id: UUID,
        node_name: str,
        started_at: datetime,
        finished_at: datetime,
        error_code: str | None = None,
    ) -> None:
        self.recorder.record_node_run(
            NodeRun(
                node_run_id=uuid4(),
                graph_run_id=run_id,
                node_name=node_name,
                node_kind="tool",
                status="failed" if error_code is not None else "completed",
                correlation_id=correlation_id,
                started_at=started_at,
                finished_at=finished_at,
                error_summary={"code": error_code} if error_code else None,
            )
        )


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
