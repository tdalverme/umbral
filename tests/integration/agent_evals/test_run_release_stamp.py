# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Run release stamp: each run references its release, 0 mutation (T029)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from tests.integration.agent.conftest import (
    build_stack,
    create_session,
    seed_profile,
    seed_user,
)
from tests.integration.chat.conftest import build_chat
from tests.integration.agent.conftest import agent_backend  # noqa: F401

from umbral.agent.runtime import ChatRuntime
from umbral.infrastructure.db.models.agent import AgentGraphRun


def _runtime_with_release(stack, *, release_id: str) -> ChatRuntime:
    return ChatRuntime(
        graph=stack.runtime.graph,
        conversation=stack.chat,
        runs=stack.runs,
        recorder=stack.recorder,
        clock=stack.runtime.clock,
        state_schema_version=stack.runtime.state_schema_version,
        topology_version=stack.runtime.topology_version,
        release_id=release_id,
    )


def test_run_stamps_its_release(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    session = create_session(factory, user_id)
    runtime = _runtime_with_release(stack, release_id="graph-release-002")
    outcome = runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
    )
    assert outcome.status == "completed"
    with factory() as db:
        row = db.get(AgentGraphRun, outcome.run_id)
        assert row is not None
        assert row.release_id == "graph-release-002"


def test_revert_does_not_mutate_prior_runs(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    chat = build_chat(factory)
    first = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    first_runtime = _runtime_with_release(stack, release_id="graph-release-001")
    first_outcome = first_runtime.run_turn(
        user_id=user_id,
        session_id=first.session_id,
        text="primera sesión",
        correlation_id=uuid4(),
    )
    second = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    second_runtime = _runtime_with_release(stack, release_id="graph-release-002")
    second_outcome = second_runtime.run_turn(
        user_id=user_id,
        session_id=second.session_id,
        text="segunda sesión",
        correlation_id=uuid4(),
    )
    with factory() as db:
        first_row = db.get(AgentGraphRun, first_outcome.run_id)
        second_row = db.get(AgentGraphRun, second_outcome.run_id)
        assert first_row is not None and first_row.release_id == "graph-release-001"
        assert second_row is not None and second_row.release_id == "graph-release-002"
        rows = db.scalars(select(AgentGraphRun)).all()
        assert len(rows) == 2
