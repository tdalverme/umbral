"""Graph unit tests: run + effects ledger (US2, FR-014/R-04)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation

from umbral.agent.graph import build_input_state, build_topology_v1
from umbral.application.agent.contracts import ModelResult
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

_REPLY_SCHEMA = {"reply_text": {"kind": "string"}, "refs": {"kind": "list"}}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _build(
    graph_clock: Callable[[], datetime] | None = None,
    gateway: Any | None = None,
) -> tuple[Any, RecordingConversation, RecordingRunRecorder]:
    conversation = RecordingConversation()
    recorder = RecordingRunRecorder()
    graph = build_topology_v1(
        gateway=gateway or FakeModelGateway(),
        conversation=conversation,
        recorder=recorder,
        saver=MemorySaver(),
        clock=graph_clock or _clock,
        model_version="local-fake",
        prompt_version="agent-chat-v1",
        schema_version="reply-v1",
        reply_schema=_REPLY_SCHEMA,
    )
    return graph, conversation, recorder


def test_single_run_persists_one_user_and_one_assistant_message() -> None:
    graph, conversation, recorder = _build()
    run_id = uuid4()
    state = build_input_state(
        run_id=run_id,
        session_id=UUID(int=20),
        user_id=UUID(int=30),
        correlation_id=UUID(int=40),
        user_message_text="hola",
    )
    config = {"configurable": {"thread_id": str(run_id)}}
    list(graph.compiled.stream(state, config, stream_mode="updates"))
    assert len(conversation.user_messages) == 1
    assert len(conversation.assistant_messages) == 1
    final = graph.compiled.get_state(config).values
    assert final["errors"] == []
    assert final["context"]["effects_applied"] == {
        "user_message": str(run_id),
        "assistant_message": str(run_id),
    }
    assert len(recorder.nodes) == 3
    assert {node.node_name for node in recorder.nodes} == {
        "start",
        "generate_reply",
        "persist_reply",
    }
    assert len(recorder.calls) == 1


def test_resume_never_reapplies_effects() -> None:
    graph, conversation, _recorder = _build()
    run_id = uuid4()
    state = build_input_state(
        run_id=run_id,
        session_id=UUID(int=20),
        user_id=UUID(int=30),
        correlation_id=UUID(int=40),
        user_message_text="hola",
    )
    config = {"configurable": {"thread_id": str(run_id)}}
    list(graph.compiled.stream(state, config, stream_mode="updates"))
    # Resume the same thread: effects are already marked, nothing is re-persisted.
    list(graph.compiled.stream(None, config, stream_mode="updates"))
    assert len(conversation.user_messages) == 1
    assert len(conversation.assistant_messages) == 1


class _FailedGateway:
    """Gateway that always returns a typed failure."""

    def generate_structured(self, **kwargs: object) -> ModelResult:
        return ModelResult(
            content=None,
            model_version="local-fake",
            status="timeout",
            latency_ms=1,
            error_code="agent.timeout",
        )


def test_generation_failure_records_error_in_state() -> None:
    graph, _conversation, recorder = _build(gateway=_FailedGateway())
    run_id = uuid4()
    state = build_input_state(
        run_id=run_id,
        session_id=UUID(int=20),
        user_id=UUID(int=30),
        correlation_id=UUID(int=40),
        user_message_text="hola",
    )
    config = {"configurable": {"thread_id": str(run_id)}}
    list(graph.compiled.stream(state, config, stream_mode="updates"))
    final = graph.compiled.get_state(config).values
    assert final["errors"] == [{"code": "agent.timeout"}]
    assert len(recorder.calls) == 1
