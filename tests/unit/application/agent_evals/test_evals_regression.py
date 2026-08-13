"""Unit tests of the strict regression gate (T018)."""

from __future__ import annotations

from typing import Any

import pytest

from umbral.application.agent_evals.contracts import (
    AgentEvalsBlocked,
    CaseEvalResult,
    EvalSuiteReport,
    GoldenConversationCase,
    GoldenDataset,
    GraphRelease,
    ReleaseActivation,
    ReleaseComponents,
)
from umbral.application.agent_evals.regression import run_regression


def _release(release_id: str) -> GraphRelease:
    return GraphRelease(
        id=release_id,
        components=ReleaseComponents(
            prompt_versions=("agent-intent-v1",),
            model_version="provider-x-model-y",
            state_schema_version="chat-state-v3",
            topology_version="chat-topology-v3",
            intent_schema_version="intent-schema-v3",
            price_table_version="price-table-v1",
            touches_prompts_or_model=False,
        ),
        owner="team-agent",
        justification="x",
        affected_case_ids=(),
        activation=ReleaseActivation(
            status="active",
            approved_by=None,
            approval_evidence=None,
            reverted_reason=None,
        ),
        date="2026-08-10",
    )


def _case(case_id: str) -> GoldenConversationCase:
    return GoldenConversationCase(
        id=case_id,
        family="onboarding",
        context={},
        turns=("hola",),
        expectation=None,  # type: ignore[arg-type]
    )


def _result(case_id: str, **overrides: object) -> CaseEvalResult:
    values: dict[str, Any] = {
        "tool_selection_ok": True,
        "args_valid": True,
        "grounding_ok": True,
        "confirmation_ok": True,
        "outcome_ok": True,
        "cost_usd": 0.01,
        "latency_ms": 10,
        "verdict": "ok",
    }
    values.update(overrides)
    return CaseEvalResult(case_id=case_id, **values)


def _report(
    *,
    baseline_results: tuple[CaseEvalResult, ...],
    candidate_results: tuple[CaseEvalResult, ...],
    baseline_release: GraphRelease,
    candidate_release: GraphRelease,
    declared_cases: frozenset[str],
    gate_enabled: bool = True,
) -> EvalSuiteReport:
    return run_regression(
        dataset=_Dataset(),
        baseline_results=baseline_results,
        candidate_results=candidate_results,
        baseline_release=baseline_release,
        candidate_release=candidate_release,
        declared_cases=declared_cases,
        cost_threshold_pct=20.0,
        latency_threshold_ms=1500,
        gate_enabled=gate_enabled,
    )


class _Dataset(GoldenDataset):
    def __init__(self) -> None:
        super().__init__(
            contract_version="1",
            registry_version="conversations-golden-v1",
            reviewed_by="unit",
            reviewed_at="2026-08-10",
            min_cases_per_family=1,
            cases=(_case("conversation-001"), _case("conversation-002")),
        )


def test_baseline_equals_candidate_passes() -> None:
    baseline = (
        _result("conversation-001"),
        _result("conversation-002"),
    )
    report = _report(
        baseline_results=baseline,
        candidate_results=baseline,
        baseline_release=_release("graph-release-001"),
        candidate_release=_release("graph-release-001"),
        declared_cases=frozenset(),
    )
    assert report.blocked is False
    assert report.metrics["tool_accuracy"] == 1.0


def test_deterministic_deviation_without_release_blocks() -> None:
    baseline = (_result("conversation-001"), _result("conversation-002"))
    candidate = (
        _result("conversation-001", tool_selection_ok=False),
        _result("conversation-002"),
    )
    with pytest.raises(AgentEvalsBlocked) as excinfo:
        _report(
            baseline_results=baseline,
            candidate_results=candidate,
            baseline_release=_release("graph-release-001"),
            candidate_release=_release("graph-release-002"),
            declared_cases=frozenset(),
        )
    assert any(
        "agent_evals.undeclared_change" in reason for reason in excinfo.value.reasons
    )
    assert any(
        "agent_evals.tool_selection_change" in reason
        for reason in excinfo.value.reasons
    )


def test_declared_release_matching_diff_passes() -> None:
    baseline = (_result("conversation-001"), _result("conversation-002"))
    candidate = (
        _result("conversation-001", tool_selection_ok=False),
        _result("conversation-002"),
    )
    report = _report(
        baseline_results=baseline,
        candidate_results=candidate,
        baseline_release=_release("graph-release-001"),
        candidate_release=_release("graph-release-002"),
        declared_cases=frozenset({"conversation-001"}),
    )
    assert report.blocked is False


def test_release_mismatch_blocks() -> None:
    baseline = (_result("conversation-001"), _result("conversation-002"))
    candidate = (
        _result("conversation-001", tool_selection_ok=False),
        _result("conversation-002"),
    )
    with pytest.raises(AgentEvalsBlocked) as excinfo:
        _report(
            baseline_results=baseline,
            candidate_results=candidate,
            baseline_release=_release("graph-release-001"),
            candidate_release=_release("graph-release-002"),
            declared_cases=frozenset({"conversation-002"}),
        )
    assert any(
        "agent_evals.release_mismatch" in reason for reason in excinfo.value.reasons
    )


def test_cost_threshold_blocks_undeclared() -> None:
    baseline = (
        _result("conversation-001", cost_usd=0.01),
        _result("conversation-002", cost_usd=0.01),
    )
    candidate = (
        _result("conversation-001", cost_usd=0.02),
        _result("conversation-002", cost_usd=0.01),
    )
    with pytest.raises(AgentEvalsBlocked) as excinfo:
        _report(
            baseline_results=baseline,
            candidate_results=candidate,
            baseline_release=_release("graph-release-001"),
            candidate_release=_release("graph-release-002"),
            declared_cases=frozenset(),
        )
    assert any("agent_evals.cost_delta" in reason for reason in excinfo.value.reasons)


def test_gate_disabled_reports_without_raising() -> None:
    baseline = (_result("conversation-001"), _result("conversation-002"))
    candidate = (
        _result("conversation-001", tool_selection_ok=False),
        _result("conversation-002"),
    )
    report = _report(
        baseline_results=baseline,
        candidate_results=candidate,
        baseline_release=_release("graph-release-001"),
        candidate_release=_release("graph-release-002"),
        declared_cases=frozenset(),
        gate_enabled=False,
    )
    assert report.blocked is True
    assert report.case_results[0].verdict == "tool_selection_change"
