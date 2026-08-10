"""Conversational runtime: run, stream, resume and deduplicate (UM-H4-005)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.agent.events import (
    RunCompleted,
    RunFailed,
    RunInterrupted,
    RunStarted,
    RuntimeEvent,
)
from umbral.agent.graph import TOPOLOGY_VERSION, AgentGraph, build_input_state
from umbral.agent.state import STATE_SCHEMA_VERSION
from umbral.application.agent.contracts import AgentRunNotFound, GraphRun
from umbral.application.agent.ports import GraphRunRepository, RunRecorder
from umbral.application.chat.contracts import ChatExecutionInProgress
from umbral.application.chat.ports import ConversationGateway

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class RunOutcome:
    run_id: UUID
    status: str
    latency_ms: int | None = None
    error_code: str | None = None


class ChatRuntime:
    """Owns one run at a time per session, with typed events and resume."""

    def __init__(
        self,
        *,
        graph: AgentGraph,
        conversation: ConversationGateway,
        runs: GraphRunRepository,
        recorder: RunRecorder,
        clock: Clock | None = None,
    ) -> None:
        self.graph = graph
        self.conversation = conversation
        self.runs = runs
        self.recorder = recorder
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run_turn(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        text: str,
        correlation_id: UUID,
        resume: bool = False,
        consumer: Callable[[RuntimeEvent], None] | None = None,
    ) -> RunOutcome:
        session = self.conversation.assert_accepts_turn(
            user_id=user_id, session_id=session_id
        )
        started_at = self.clock()
        existing = self.runs.active_for_session(session_id) if resume else None
        if resume and existing is None:
            raise AgentRunNotFound()
        run_id = existing.run_id if existing is not None else uuid4()
        attempt = (existing.attempt if existing is not None else 0) + 1
        run = GraphRun(
            run_id=run_id,
            session_id=session.session_id,
            state_schema_version=STATE_SCHEMA_VERSION,
            topology_version=TOPOLOGY_VERSION,
            status="running",
            attempt=attempt,
            correlation_id=correlation_id,
            started_at=started_at,
        )
        if existing is None:
            claimed = self.runs.create(run)
            if claimed is None:
                active = self.runs.active_for_session(session_id)
                raise ChatExecutionInProgress(
                    active.run_id if active is not None else None
                )
        else:
            self.runs.mark(run_id, status="running", attempt=attempt)

        self.graph.deps.sinks.emit = consumer or (lambda _event: None)
        emit = self.graph.deps.sinks.emit
        emit(
            RunStarted(
                run_id=run_id,
                session_id=session.session_id,
                correlation_id=correlation_id,
            )
        )
        config = {"configurable": {"thread_id": str(run_id)}}
        try:
            if existing is None:
                stream_input = build_input_state(
                    run_id=run_id,
                    session_id=session.session_id,
                    user_id=user_id,
                    correlation_id=correlation_id,
                    user_message_text=text,
                )
            else:
                stream_input = None
            for _chunk in self.graph.compiled.stream(
                stream_input, config, stream_mode="updates"
            ):
                pass
            values = self.graph.compiled.get_state(config).values
            if values.get("schema_version") != STATE_SCHEMA_VERSION:
                finished = self.clock()
                latency_ms = _elapsed_ms(run.started_at, finished)
                self.runs.mark(
                    run_id,
                    status="failed",
                    finished_at=finished,
                    latency_ms=latency_ms,
                    error_summary={"code": "agent.state_incompatible"},
                )
                emit(RunFailed(run_id=run_id, error_code="agent.state_incompatible"))
                return RunOutcome(
                    run_id=run_id,
                    status="failed",
                    latency_ms=latency_ms,
                    error_code="agent.state_incompatible",
                )
            errors = list(values.get("errors") or [])
            context = dict(values.get("context") or {})
            usage = dict(context.get("token_usage") or {})
            finished = self.clock()
            latency_ms = _elapsed_ms(run.started_at, finished)
            if errors:
                error = dict(errors[0])
                self.runs.mark(
                    run_id,
                    status="failed",
                    finished_at=finished,
                    latency_ms=latency_ms,
                    error_summary=error,
                    token_usage=usage or None,
                )
                emit(
                    RunFailed(
                        run_id=run_id,
                        error_code=str(error.get("code", "agent.failed")),
                    )
                )
                return RunOutcome(
                    run_id=run_id,
                    status="failed",
                    latency_ms=latency_ms,
                    error_code=str(error.get("code", "agent.failed")),
                )
            self.runs.mark(
                run_id,
                status="completed",
                finished_at=finished,
                latency_ms=latency_ms,
                token_usage=usage or None,
            )
            message_id = context.get("assistant_message_id")
            emit(
                RunCompleted(
                    run_id=run_id,
                    message_id=UUID(str(message_id)) if message_id else None,
                )
            )
            return RunOutcome(run_id=run_id, status="completed", latency_ms=latency_ms)
        except Exception:
            finished = self.clock()
            latency_ms = _elapsed_ms(run.started_at, finished)
            self.runs.mark(
                run_id,
                status="interrupted",
                finished_at=finished,
                latency_ms=latency_ms,
                error_summary={"code": "agent.interrupted"},
            )
            emit(RunInterrupted(run_id=run_id))
            return RunOutcome(
                run_id=run_id,
                status="interrupted",
                latency_ms=latency_ms,
                error_code="agent.interrupted",
            )


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)
