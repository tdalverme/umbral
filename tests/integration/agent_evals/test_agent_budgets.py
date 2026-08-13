# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Budget enforcement over the real runtime + Postgres (T033)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from tests.integration.agent.conftest import (
    build_stack,
    create_session,
    seed_profile,
    seed_user,
)
from tests.integration.chat.conftest import build_chat

from umbral.agent.events import BudgetWarning, RuntimeEvent
from umbral.agent.runtime import ChatRuntime
from umbral.application.agent.budgets import BudgetPolicy
from umbral.application.agent.contracts import (
    AgentBudgetExhausted,
    AgentRateLimitExceeded,
)
from umbral.application.agent_evals.price import load_price_table
from umbral.infrastructure.agent.budgets import (
    SettingsBudgetGate,
    SqlAlchemyBudgetConsumptionSource,
)


def _runtime(stack, *, policy: BudgetPolicy) -> ChatRuntime:
    price_table = load_price_table(
        Path("contracts/agent-evals/v1/price-table-v1.json")
    )
    gate = SettingsBudgetGate(
        source=SqlAlchemyBudgetConsumptionSource(stack.factory, price_table),
        policy=policy,
        clock=stack.runtime.clock,
    )
    return ChatRuntime(
        graph=stack.runtime.graph,
        conversation=stack.chat,
        runs=stack.runs,
        recorder=stack.recorder,
        clock=stack.runtime.clock,
        state_schema_version=stack.runtime.state_schema_version,
        topology_version=stack.runtime.topology_version,
        budget_gate=gate,
    )


def test_turn_emits_budget_warning_without_interruption(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    session = create_session(factory, user_id)
    runtime = _runtime(
        stack,
        policy=BudgetPolicy(session_token_cap=1_000_000, user_token_cap=1_000_000),
    )
    runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="primer turno que consume tokens",
        correlation_id=uuid4(),
    )
    events: list[RuntimeEvent] = []
    policy = BudgetPolicy(
        session_token_cap=100, user_token_cap=100, warning_ratio=0.001
    )
    runtime = _runtime(stack, policy=policy)
    outcome = runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="segundo turno con advertencia",
        correlation_id=uuid4(),
        consumer=events.append,
    )
    assert outcome.status == "completed"
    assert any(isinstance(event, BudgetWarning) for event in events)


def test_exhaustion_after_a_turn_blocks_the_next_turn(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    session = create_session(factory, user_id)
    policy = BudgetPolicy(session_token_cap=1_000_000, user_token_cap=1_000_000)
    runtime = _runtime(stack, policy=policy)
    first = runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
    )
    assert first.status == "completed"
    tiny = BudgetPolicy(session_token_cap=1, user_token_cap=1)
    exhausted = _runtime(stack, policy=tiny)
    with pytest.raises(AgentBudgetExhausted) as excinfo:
        exhausted.run_turn(
            user_id=user_id,
            session_id=session.session_id,
            text="otro turno",
            correlation_id=uuid4(),
        )
    assert excinfo.value.code == "agent.budget_exhausted"
    assert excinfo.value.kind == "session_tokens"


def test_concurrency_cap_blocks_with_rate_limit_error(agent_backend) -> None:
    from sqlalchemy import select

    from umbral.infrastructure.db.models.agent import AgentGraphRun
    from umbral.infrastructure.db.models.chat import ChatSession

    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    chat = build_chat(factory)
    profile = seed_profile(factory, user_id)
    session = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    now = datetime.now(timezone.utc)
    with factory() as db:
        row = db.scalars(
            select(AgentGraphRun)
            .join(ChatSession, ChatSession.id == AgentGraphRun.session_id)
            .where(ChatSession.user_id == user_id)
            .limit(1)
        ).first()
        if row is None:
            db.add(
                AgentGraphRun(
                    session_id=session.session_id,
                    state_schema_version=1,
                    topology_version=1,
                    status="running",
                    attempt=1,
                    started_at=now,
                    created_at=now,
                    updated_at=now,
                    source="agent.graph_run",
                    correlation_id=uuid4(),
                )
            )
            db.commit()
    policy = BudgetPolicy(user_concurrency_cap=1)
    runtime = _runtime(stack, policy=policy)
    with pytest.raises(AgentRateLimitExceeded) as excinfo:
        runtime.run_turn(
            user_id=user_id,
            session_id=session.session_id,
            text="hola",
            correlation_id=uuid4(),
        )
    assert excinfo.value.code == "agent.rate_limit_exceeded"


def test_other_users_do_not_consume_this_users_budget(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    first_user = seed_user(factory)
    first_session = create_session(factory, first_user)
    _runtime(
        stack,
        policy=BudgetPolicy(session_token_cap=1_000_000, user_token_cap=1_000_000),
    ).run_turn(
        user_id=first_user,
        session_id=first_session.session_id,
        text="consume tokens del primer usuario",
        correlation_id=uuid4(),
    )
    second_user = seed_user(factory)
    second_session = create_session(factory, second_user)
    runtime = _runtime(stack, policy=BudgetPolicy(user_token_cap=100))
    outcome = runtime.run_turn(
        user_id=second_user,
        session_id=second_session.session_id,
        text="el segundo usuario no hereda el consumo",
        correlation_id=uuid4(),
    )
    assert outcome.status == "completed"
