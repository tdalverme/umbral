"""Runtime v3: interrupt detection and decision resume (FR-011, R-04)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from tests.support.agent import InMemoryGraphRunRepository, RecordingRunRecorder
from tests.support.chat import RecordingConversation

from umbral.agent.events import InterruptWaiting, RunStarted
from umbral.agent.graph import GraphSinks
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import CHAT_STATE_SCHEMA_VERSION, AgentState

_INTERRUPT_PAYLOAD = {
    "type": "proposal_decision",
    "proposal_id": "proposal-1",
    "diff": {"budget_max": 900},
    "impact": {"fields_changed": ["budget_max"]},
    "expires_at": "2026-08-11T00:00:00Z",
}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _wait_decision(state: AgentState) -> dict[str, object]:
    decision = interrupt(_INTERRUPT_PAYLOAD)
    return {
        "schema_version": CHAT_STATE_SCHEMA_VERSION,
        "context": {"decision": decision},
        "errors": [],
    }


def _build_runtime() -> tuple[ChatRuntime, list[object]]:
    builder = StateGraph(AgentState)
    builder.add_node("wait_decision", _wait_decision)
    builder.add_edge(START, "wait_decision")
    builder.add_edge("wait_decision", END)
    holder = type(
        "TestGraph",
        (),
        {"compiled": builder.compile(checkpointer=MemorySaver()), "deps": type(
            "Deps", (), {"sinks": GraphSinks()}
        )()},
    )()
    conversation = RecordingConversation()
    events: list[object] = []
    runtime = ChatRuntime(
        graph=holder,
        conversation=conversation,
        runs=InMemoryGraphRunRepository(),
        recorder=RecordingRunRecorder(),
        clock=_clock,
        state_schema_version=CHAT_STATE_SCHEMA_VERSION,
        topology_version=3,
    )
    return runtime, events


def test_interrupt_is_detected_and_run_marks_interrupted() -> None:
    runtime, events = _build_runtime()
    session_id = UUID(int=20)
    user_id = UUID(int=30)
    outcome = runtime.run_turn(
        user_id=user_id,
        session_id=session_id,
        text="subí el presupuesto a 900",
        correlation_id=UUID(int=40),
        consumer=events.append,
    )
    assert outcome.status == "interrupted"
    assert outcome.interrupt == _INTERRUPT_PAYLOAD
    assert any(isinstance(event, InterruptWaiting) for event in events)
    assert isinstance(events[0], RunStarted)
    run = runtime.runs.get(outcome.run_id)
    assert run is not None and run.status == "interrupted"


def test_resume_with_decision_completes_same_run() -> None:
    runtime, events = _build_runtime()
    session_id = UUID(int=20)
    user_id = UUID(int=30)
    first = runtime.run_turn(
        user_id=user_id,
        session_id=session_id,
        text="subí el presupuesto a 900",
        correlation_id=UUID(int=40),
        consumer=events.append,
    )
    assert first.status == "interrupted"
    second = runtime.run_turn(
        user_id=user_id,
        session_id=session_id,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "approve", "proposal_id": "proposal-1"},
        consumer=events.append,
    )
    assert second.run_id == first.run_id
    assert second.status == "completed"
    assert second.interrupt is None
    run = runtime.runs.get(second.run_id)
    assert run is not None and run.status == "completed"


def test_resume_without_active_run_raises_not_found() -> None:
    runtime, _events = _build_runtime()
    try:
        runtime.run_turn(
            user_id=UUID(int=30),
            session_id=UUID(int=99),
            text="",
            correlation_id=uuid4(),
            resume=True,
        )
    except Exception as exc:  # noqa: BLE001
        assert type(exc).__name__ == "AgentRunNotFound"
    else:
        raise AssertionError("expected AgentRunNotFound")
