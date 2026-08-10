# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Eval suite lifecycle over the real v3 stack + Postgres (T026)."""

from __future__ import annotations

from datetime import datetime, timezone

from tests.integration.agent_evals.conftest import eval_backend, eval_context  # noqa: F401

from umbral.application.agent_evals.regression import run_regression
from umbral.application.agent_evals.runner import run_suite
from umbral.infrastructure.agent_evals.repositories import (
    SqlAlchemyEvalSuiteRepository,
)
from umbral.infrastructure.db.models.agent_evals import AgentEvalCaseResult, AgentEvalSuite


def test_suite_runs_over_the_published_dataset(eval_context) -> None:
    release = eval_context.releases.active_release()
    assert release is not None
    results = run_suite(
        executor=eval_context.executor,
        dataset=eval_context.dataset,
        release=release,
        price_table=eval_context.price_table,
    )
    assert len(results) == len(eval_context.dataset.cases)
    for result in results:
        assert result.tool_selection_ok, result.case_id
        assert result.args_valid, result.case_id
        assert result.grounding_ok, result.case_id
        assert result.confirmation_ok, result.case_id
        assert result.outcome_ok, result.case_id
        assert result.cost_usd >= 0


def test_two_runs_of_the_same_suite_are_reproducible(eval_context) -> None:
    release = eval_context.releases.active_release()
    assert release is not None
    first = run_suite(
        executor=eval_context.executor,
        dataset=eval_context.dataset,
        release=release,
        price_table=eval_context.price_table,
    )
    second = run_suite(
        executor=eval_context.executor,
        dataset=eval_context.dataset,
        release=release,
        price_table=eval_context.price_table,
    )
    first_signals = [(r.case_id, r.tool_selection_ok, r.args_valid, r.grounding_ok, r.outcome_ok) for r in first]
    second_signals = [(r.case_id, r.tool_selection_ok, r.args_valid, r.grounding_ok, r.outcome_ok) for r in second]
    assert first_signals == second_signals


def test_suite_results_are_persisted(eval_context) -> None:
    release = eval_context.releases.active_release()
    assert release is not None
    results = run_suite(
        executor=eval_context.executor,
        dataset=eval_context.dataset,
        release=release,
        price_table=eval_context.price_table,
    )
    repo = SqlAlchemyEvalSuiteRepository(eval_context.factory)
    now = datetime.now(timezone.utc)
    report = run_regression(
        dataset=eval_context.dataset,
        baseline_results=results,
        candidate_results=results,
        baseline_release=release,
        candidate_release=release,
        declared_cases=frozenset(),
        cost_threshold_pct=20.0,
        latency_threshold_ms=1500,
        gateway_fidelity="simulated",
    )
    suite_id = repo.create_suite(report=report, started_at=now, finished_at=now)
    for result in results:
        repo.append_case_result(suite_id=suite_id, result=result)
    with eval_context.factory() as db:
        suite = db.get(AgentEvalSuite, suite_id)
        assert suite is not None
        assert suite.status == "passed"
        assert suite.gateway_fidelity == "simulated"
        results_count = db.query(AgentEvalCaseResult).filter(
            AgentEvalCaseResult.eval_suite_id == suite_id
        ).count()
        assert results_count == len(eval_context.dataset.cases)


def test_regression_gate_blocks_an_undeclared_change(eval_context) -> None:
    release = eval_context.releases.active_release()
    assert release is not None
    baseline = run_suite(
        executor=eval_context.executor,
        dataset=eval_context.dataset,
        release=release,
        price_table=eval_context.price_table,
    )
    from dataclasses import replace

    tampered = [
        replace(result, tool_selection_ok=False)
        if result.case_id == "conversation-001"
        else result
        for result in baseline
    ]
    report = run_regression(
        dataset=eval_context.dataset,
        baseline_results=baseline,
        candidate_results=tampered,
        baseline_release=release,
        candidate_release=release,
        declared_cases=frozenset(),
        cost_threshold_pct=20.0,
        latency_threshold_ms=1500,
        gate_enabled=False,
    )
    assert report.blocked is True
    assert any(
        "agent_evals.tool_selection_change" in reason for reason in report.reasons
    )
