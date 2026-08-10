"""Runtime e2e integration tests (US2, SC-005): run, concurrency, resume."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.integration.agent.conftest import (
    build_stack,
    create_session,
    seed_user,
)

from umbral.application.agent.contracts import GraphRun
from umbral.application.chat.contracts import ChatExecutionInProgress
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway
from umbral.infrastructure.db.models.agent import (
    AgentGraphRun,
    AgentModelCall,
    AgentNodeRun,
)

SessionFactory = Callable[[], Session]
Backend = tuple[SessionFactory, str]

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _count(factory: SessionFactory, model: Any, column: Any, value: Any) -> int:
    with factory() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(model).where(column == value)
            )
        )


def test_full_turn_persists_one_and_one_and_records_audit(
    agent_backend: Backend,
) -> None:
    factory, url = agent_backend
    stack = build_stack(factory, url)
    owner = seed_user(factory)
    session = create_session(factory, owner)

    events: list[Any] = []
    outcome = stack.runtime.run_turn(
        user_id=owner,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
        consumer=events.append,
    )
    assert outcome.status == "completed"

    run = stack.runs.get(outcome.run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.attempt == 1
    assert run.latency_ms is not None

    history = stack.chat.list_history(user_id=owner, session_id=session.session_id)
    assert [message.role for message in history] == ["user", "assistant"]
    assistant_run_ids = [
        message.graph_run_id for message in history if message.role == "assistant"
    ]
    assert assistant_run_ids == [outcome.run_id]

    assert [type(event).__name__ for event in events] == [
        "RunStarted",
        "ReplyFragment",
        "RunCompleted",
    ]
    assert _count(factory, AgentNodeRun, AgentNodeRun.graph_run_id, outcome.run_id) == 3
    assert (
        _count(factory, AgentModelCall, AgentModelCall.graph_run_id, outcome.run_id)
        == 1
    )
    with factory() as db:
        row = db.scalar(select(AgentGraphRun).where(AgentGraphRun.id == outcome.run_id))
        assert row is not None
        assert row.token_usage is not None
        assert row.token_usage["total"] == 24  # fake gateway 8 + 16


def test_second_turn_during_active_run_is_rejected(agent_backend: Backend) -> None:
    factory, url = agent_backend
    stack = build_stack(factory, url)
    owner = seed_user(factory)
    session = create_session(factory, owner)

    blocker = GraphRun(
        run_id=uuid4(),
        session_id=session.session_id,
        state_schema_version=1,
        topology_version=1,
        status="running",
        attempt=1,
        correlation_id=uuid4(),
        started_at=_NOW,
    )
    assert stack.runs.create(blocker) is not None
    with pytest.raises(ChatExecutionInProgress):
        stack.runtime.run_turn(
            user_id=owner,
            session_id=session.session_id,
            text="otro",
            correlation_id=uuid4(),
        )


def test_interruption_and_resume_never_duplicate_effects(
    agent_backend: Backend,
) -> None:
    factory, url = agent_backend
    gateway = FakeModelGateway(raise_on_call=1)
    stack = build_stack(factory, url, gateway=gateway)
    owner = seed_user(factory)
    session = create_session(factory, owner)

    first = stack.runtime.run_turn(
        user_id=owner,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
    )
    assert first.status == "interrupted"
    run = stack.runs.get(first.run_id)
    assert run is not None
    assert run.status == "interrupted"
    assert run.attempt == 1

    # No partial assistant message is persisted after an interruption (R-11).
    history = stack.chat.list_history(user_id=owner, session_id=session.session_id)
    assert [message.role for message in history] == ["user"]

    second = stack.runtime.run_turn(
        user_id=owner,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
        resume=True,
    )
    assert second.status == "completed"
    resumed = stack.runs.get(second.run_id)
    assert resumed is not None
    assert resumed.status == "completed"
    assert resumed.attempt == 2

    history = stack.chat.list_history(user_id=owner, session_id=session.session_id)
    assert [message.role for message in history] == ["user", "assistant"]
    assert len(gateway.calls) == 2


def test_resume_without_interrupted_run_raises(agent_backend: Backend) -> None:
    from umbral.application.agent.contracts import AgentRunNotFound

    factory, url = agent_backend
    stack = build_stack(factory, url)
    owner = seed_user(factory)
    session = create_session(factory, owner)
    with pytest.raises(AgentRunNotFound):
        stack.runtime.run_turn(
            user_id=owner,
            session_id=session.session_id,
            text="hola",
            correlation_id=uuid4(),
            resume=True,
        )
