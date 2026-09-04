"""Single semantic conversation runtime: run, stream, resume and deduplicate."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from langgraph.types import Command

from umbral.agent.events import (
    BudgetWarning,
    InterruptWaiting,
    ReplyFragment,
    RunCompleted,
    RunFailed,
    RunInterrupted,
    RunStarted,
    RuntimeEvent,
)
from umbral.agent.graph import AgentGraph
from umbral.application.agent.budgets import BudgetGate
from umbral.application.agent.contracts import (
    AgentBudgetExhausted,
    AgentRateLimitExceeded,
    AgentRunNotFound,
    GraphRun,
)
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
    interrupt: dict[str, Any] | None = None


class ChatRuntime:
    """Owns one run at a time per session over the single agent graph."""

    def __init__(
        self,
        *,
        graph: AgentGraph,
        conversation: ConversationGateway,
        runs: GraphRunRepository,
        recorder: RunRecorder | None = None,
        clock: Clock | None = None,
        release_id: str | None = None,
        budget_gate: BudgetGate | None = None,
    ) -> None:
        self.graph = graph
        self.conversation = conversation
        self.runs = runs
        self.recorder = recorder
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.release_id = release_id
        self.budget_gate = budget_gate

    def run_turn(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        text: str,
        correlation_id: UUID,
        resume: bool = False,
        decision: Mapping[str, object] | None = None,
        consumer: Callable[[RuntimeEvent], None] | None = None,
        client_message_id: UUID | None = None,
        context: Mapping[str, object] | None = None,
    ) -> RunOutcome:
        session = self.conversation.assert_accepts_turn(
            user_id=user_id, session_id=session_id
        )
        started_at = self.clock()
        emit = consumer or (lambda _event: None)
        if self.budget_gate is not None:
            verdict = self.budget_gate.check(user_id=user_id, session_id=session_id)
            if verdict.level == "exhausted":
                if verdict.kind == "concurrency":
                    raise AgentRateLimitExceeded("concurrency")
                raise AgentBudgetExhausted(str(verdict.kind or "budget"))
            if verdict.level == "warning":
                emit(
                    BudgetWarning(
                        run_id=None,
                        session_id=session.session_id,
                        ratio=verdict.ratio or 0.0,
                    )
                )
        existing = self.runs.active_for_session(session_id) if resume else None
        if resume and existing is None:
            raise AgentRunNotFound()
        run_id = existing.run_id if existing is not None else uuid4()
        attempt = (existing.attempt if existing is not None else 0) + 1
        run = GraphRun(
            run_id=run_id,
            session_id=session.session_id,
            state_schema_version=1,
            topology_version=1,
            status="running",
            attempt=attempt,
            correlation_id=correlation_id,
            started_at=started_at,
            release_id=self.release_id,
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

        emit(
            RunStarted(
                run_id=run_id,
                session_id=session.session_id,
                correlation_id=correlation_id,
            )
        )
        config = {
            "configurable": {
                "thread_id": str(run_id),
                "user_id": str(user_id),
                "session_id": str(session.session_id),
                "correlation_id": str(correlation_id),
            }
        }
        compiled = self.graph.compiled
        try:
            if existing is None:
                self.conversation.append_user_message(
                    user_id=user_id,
                    session_id=session.session_id,
                    text=text,
                    correlation_id=correlation_id,
                    client_message_id=client_message_id,
                    context=context,
                )
                stream_input: object = {
                    "contract_version": "5",
                    "schema_version": "conversation-state",
                    "message_id": str(run_id),
                    "message_text": text,
                }
            elif decision is not None:
                stream_input = Command(resume=dict(decision))
            else:
                stream_input = None
            interrupt_payload: dict[str, Any] | None = None
            for chunk in compiled.stream(
                stream_input, config, stream_mode="updates"
            ):
                interrupt = _interrupt_from_chunk(chunk)
                if interrupt is not None:
                    interrupt_payload = interrupt
                    break
            values = compiled.get_state(config).values
            if interrupt_payload is not None:
                finished = self.clock()
                latency_ms = _elapsed_ms(run.started_at, finished)
                self.runs.mark(
                    run_id,
                    status="interrupted",
                    finished_at=finished,
                    latency_ms=latency_ms,
                    error_summary={"code": "agent.interrupt_proposal_decision"},
                )
                emit(InterruptWaiting(run_id=run_id, interrupt=interrupt_payload))
                return RunOutcome(
                    run_id=run_id,
                    status="interrupted",
                    latency_ms=latency_ms,
                    interrupt=interrupt_payload,
                )
            errors = list(values.get("errors") or [])
            failure_stage = values.get("failure_stage")
            if failure_stage is not None:
                errors = errors or [{"code": f"agent.{failure_stage}"}]
            reply = values.get("reply")
            if isinstance(reply, Mapping) and str(reply.get("text") or ""):
                emit(ReplyFragment(run_id=run_id, delta=str(reply.get("text"))))
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
            assistant_message = self.conversation.persist_assistant_message(
                user_id=user_id,
                session_id=session.session_id,
                text=str(reply.get("text") or "")
                if isinstance(reply, Mapping)
                else "",
                refs=_message_refs(reply),
                graph_run_id=run_id,
                correlation_id=correlation_id,
            )
            self.runs.mark(
                run_id,
                status="completed",
                finished_at=finished,
                latency_ms=latency_ms,
            )
            emit(RunCompleted(run_id=run_id, message_id=assistant_message.message_id))
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


def _interrupt_from_chunk(chunk: object) -> dict[str, Any] | None:
    """Extract the interrupt payload from a stream chunk, if any."""
    if not isinstance(chunk, Mapping):
        return None
    raw = chunk.get("__interrupt__")
    if not raw:
        return None
    value = None
    if isinstance(raw, (list, tuple)) and len(raw) > 0:
        item = raw[0]
        value = getattr(item, "value", item)
    if not isinstance(value, Mapping):
        return None
    return dict(value)


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


def _message_refs(reply: object) -> tuple[Mapping[str, str], ...]:
    """Project reply refs into the narrower durable chat-message contract."""
    if not isinstance(reply, Mapping):
        return ()
    raw_refs = reply.get("verified_refs")
    if not isinstance(raw_refs, (list, tuple)):
        return ()
    refs: list[Mapping[str, str]] = []
    for raw_ref in raw_refs:
        if isinstance(raw_ref, Mapping):
            entity = raw_ref.get("entity")
            ref_id = raw_ref.get("id")
        elif isinstance(raw_ref, str):
            entity, separator, ref_id = raw_ref.partition(":")
            if not separator:
                continue
        else:
            continue
        if entity in {"listing", "comparison"} and isinstance(ref_id, str) and ref_id:
            refs.append({"entity": entity, "id": ref_id})
    return tuple(refs)
