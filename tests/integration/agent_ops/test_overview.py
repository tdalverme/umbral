# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Agent ops dashboard aggregates match the source records (T039)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tests.integration.agent.conftest import (
    build_stack,
    create_session,
    seed_user,
)

from umbral.application.agent_evals.contracts import EvalSuiteReport
from umbral.application.agent_evals.price import load_price_table
from umbral.infrastructure.agent_evals.repositories import (
    SqlAlchemyEvalSuiteRepository,
)
from umbral.infrastructure.agent_ops.overview import SqlAlchemyOpsRunRepository


def test_overview_aggregates_match_the_source_records(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    session = create_session(factory, user_id)
    outcome = stack.runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="turno para generar runs y model calls",
        correlation_id=uuid4(),
    )
    assert outcome.status == "completed"

    price_table = load_price_table(Path("contracts/agent-evals/v1/price-table-v1.json"))
    now = datetime.now(timezone.utc)
    repo = SqlAlchemyEvalSuiteRepository(factory)
    report = EvalSuiteReport(
        dataset_version="conversations-golden-v1",
        baseline_release_id="graph-release-001",
        candidate_release_id="graph-release-002",
        gateway_fidelity="simulated",
        metrics={"tool_accuracy": 0.5},
        case_results=(),
        blocked=True,
        reasons=("agent_evals.undeclared_change:conversation-001",),
    )
    repo.create_suite(report=report, started_at=now, finished_at=now)

    ops = SqlAlchemyOpsRunRepository(
        factory, price_table, clock=lambda: now
    ).overview()
    assert ops.tokens_total > 0
    assert ops.cost_total_usd >= 0
    assert ops.latency_p95_ms >= 0
    assert ops.tool_success_rate == 1.0
    assert len(ops.eval_regressions) == 1
    regression = ops.eval_regressions[0]
    assert regression.candidate_release_id == "graph-release-002"
    assert regression.blocked is True
    assert "agent_evals.undeclared_change" in regression.reasons[0]
    assert ops.data_as_of == now


def test_overview_exposes_no_pii(agent_backend) -> None:
    factory, _url = agent_backend
    stack = build_stack(factory, _url)
    user_id = seed_user(factory)
    session = create_session(factory, user_id)
    stack.runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="turno",
        correlation_id=uuid4(),
    )
    price_table = load_price_table(Path("contracts/agent-evals/v1/price-table-v1.json"))
    overview = SqlAlchemyOpsRunRepository(factory, price_table).overview()
    from dataclasses import asdict

    payload = asdict(overview)
    for key, value in payload.items():
        assert "user" not in str(key).lower()
        if isinstance(value, str):
            assert "usuario" not in value
