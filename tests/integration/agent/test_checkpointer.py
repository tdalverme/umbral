"""Postgres checkpointer integration tests (US3, FR-007/FR-008)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from sqlalchemy.orm import Session
from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation

from umbral.agent.graph import build_input_state, build_topology_v1
from umbral.infrastructure.agent.checkpointer import (
    close_postgres_saver,
    create_postgres_saver,
)
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

SessionFactory = Callable[[], Session]
Backend = tuple[SessionFactory, str]

REPLY_SCHEMA = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "refs": {"kind": "list"},
}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def test_saver_setup_creates_langgraph_tables(agent_backend: Backend) -> None:
    factory, url = agent_backend
    saver = create_postgres_saver(url, strict_msgpack=True)
    try:
        with factory() as session:
            rows = session.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename LIKE 'checkpoint%'"
                )
            )
            names = {row[0] for row in rows}
        assert {
            "checkpoints",
            "checkpoint_writes",
            "checkpoint_blobs",
            "checkpoint_migrations",
        } <= names
    finally:
        close_postgres_saver(saver)


def test_thread_survives_requests_and_can_be_deleted(agent_backend: Backend) -> None:
    factory, url = agent_backend
    saver = create_postgres_saver(url, strict_msgpack=True)
    try:
        graph = build_topology_v1(
            gateway=FakeModelGateway(),
            conversation=RecordingConversation(),
            recorder=RecordingRunRecorder(),
            saver=saver,
            clock=_clock,
            model_version="local-fake",
            prompt_version="agent-chat-v1",
            schema_version="reply-v1",
            reply_schema=REPLY_SCHEMA,
        )
        run_id = uuid4()
        config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
        state = build_input_state(
            run_id=run_id,
            session_id=UUID(int=2),
            user_id=UUID(int=3),
            correlation_id=UUID(int=4),
            user_message_text="hola",
        )
        list(graph.compiled.stream(state, config, stream_mode="updates"))
        assert saver.get_tuple(config) is not None

        # Isolation by thread id: a different thread has no checkpoint.
        other: RunnableConfig = {"configurable": {"thread_id": str(uuid4())}}
        assert saver.get_tuple(other) is None

        saver.delete_thread(str(run_id))
        assert saver.get_tuple(config) is None
    finally:
        close_postgres_saver(saver)
