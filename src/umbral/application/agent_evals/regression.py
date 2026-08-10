"""Strict regression gate over the golden dataset (clarification Q2, R-07).

The gate compares a baseline and a candidate eval suite on the SAME golden
dataset. Deterministic signals (tool selection, args, grounding,
confirmation, outcome) block on any flip with 0 tolerance; cost and latency
use policy thresholds. Declared affected cases must match the detected diff
exactly (H3.4 convention).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from umbral.application.agent_evals.contracts import (
    AgentEvalsBlocked,
    CaseEvalResult,
    EvalSuiteReport,
    EvalVerdict,
    GatewayFidelity,
    GoldenDataset,
    GraphRelease,
)

_DETERMINISTIC_SIGNALS: tuple[tuple[str, str], ...] = (
    ("tool_selection_ok", "tool_selection_change"),
    ("args_valid", "args_change"),
    ("grounding_ok", "grounding_change"),
    ("confirmation_ok", "confirmation_change"),
    ("outcome_ok", "outcome_change"),
)


def run_regression(
    *,
    dataset: GoldenDataset,
    baseline_results: Sequence[CaseEvalResult],
    candidate_results: Sequence[CaseEvalResult],
    baseline_release: GraphRelease,
    candidate_release: GraphRelease,
    declared_cases: frozenset[str],
    cost_threshold_pct: float,
    latency_threshold_ms: int,
    gateway_fidelity: GatewayFidelity = "simulated",
    gate_enabled: bool = True,
) -> EvalSuiteReport:
    """Compare baseline vs candidate suites and produce the gate report.

    Raises :class:`AgentEvalsBlocked` when the gate is enabled and any change
    is undeclared or mismatched; the report carries the same reasons.
    """
    baseline_by_case = {item.case_id: item for item in baseline_results}
    candidate_by_case = {item.case_id: item for item in candidate_results}
    results: list[CaseEvalResult] = []
    changed_case_ids: set[str] = set()
    for case in dataset.cases:
        baseline = baseline_by_case[case.id]
        candidate = candidate_by_case[case.id]
        verdict, reason, changed = _case_verdict(
            baseline=baseline,
            candidate=candidate,
            cost_threshold_pct=cost_threshold_pct,
            latency_threshold_ms=latency_threshold_ms,
        )
        results.append(
            CaseEvalResult(
                case_id=case.id,
                tool_selection_ok=candidate.tool_selection_ok,
                args_valid=candidate.args_valid,
                grounding_ok=candidate.grounding_ok,
                confirmation_ok=candidate.confirmation_ok,
                outcome_ok=candidate.outcome_ok,
                cost_usd=candidate.cost_usd,
                latency_ms=candidate.latency_ms,
                verdict=verdict,
                reason=reason,
            )
        )
        if changed:
            changed_case_ids.add(case.id)
    declared = set(declared_cases)
    reasons = _gate_reasons(
        changed_case_ids=changed_case_ids,
        declared=declared,
        results=tuple(results),
    )
    report = EvalSuiteReport(
        dataset_version=dataset.registry_version,
        baseline_release_id=baseline_release.id,
        candidate_release_id=candidate_release.id,
        gateway_fidelity=gateway_fidelity,
        metrics=_aggregate_metrics(tuple(results)),
        case_results=tuple(results),
        blocked=bool(reasons),
        reasons=reasons,
    )
    if gate_enabled and report.blocked:
        raise AgentEvalsBlocked(reasons)
    return report


def _case_verdict(
    *,
    baseline: CaseEvalResult,
    candidate: CaseEvalResult,
    cost_threshold_pct: float,
    latency_threshold_ms: int,
) -> tuple[EvalVerdict, str, bool]:
    for field, verdict in _DETERMINISTIC_SIGNALS:
        if getattr(baseline, field) and not getattr(candidate, field):
            return (
                cast(EvalVerdict, verdict),
                f"{verdict} for {candidate.case_id}",
                True,
            )
    if baseline.cost_usd > 0 and candidate.cost_usd > 0:
        delta_pct = (candidate.cost_usd - baseline.cost_usd) / baseline.cost_usd * 100
        if delta_pct > cost_threshold_pct:
            return (
                "cost_delta",
                f"cost +{delta_pct:.1f}% for {candidate.case_id}",
                True,
            )
    if candidate.latency_ms > baseline.latency_ms + latency_threshold_ms:
        return (
            "latency_delta",
            f"latency +{candidate.latency_ms - baseline.latency_ms}ms "
            f"for {candidate.case_id}",
            True,
        )
    return ("ok", "", False)


def _gate_reasons(
    *,
    changed_case_ids: set[str],
    declared: set[str],
    results: tuple[CaseEvalResult, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if changed_case_ids:
        undeclared = sorted(changed_case_ids - declared)
        extra = sorted(declared - changed_case_ids)
        if undeclared:
            reasons.append(f"agent_evals.undeclared_change:{','.join(undeclared)}")
        if extra:
            reasons.append(f"agent_evals.release_mismatch:{','.join(extra)}")
    for result in results:
        if result.verdict != "ok" and result.case_id not in declared:
            reasons.append(f"agent_evals.{result.verdict}:{result.case_id}")
    return tuple(dict.fromkeys(reasons))


def _aggregate_metrics(results: tuple[CaseEvalResult, ...]) -> Mapping[str, float]:
    total = max(1, len(results))
    costs = [item.cost_usd for item in results]
    latencies = [item.latency_ms for item in results]
    return {
        "tool_accuracy": sum(item.tool_selection_ok for item in results) / total,
        "args_valid_rate": sum(item.args_valid for item in results) / total,
        "grounding_coverage": sum(item.grounding_ok for item in results) / total,
        "confirmation_rate": sum(item.confirmation_ok for item in results) / total,
        "outcome_match": sum(item.outcome_ok for item in results) / total,
        "cost_per_case_avg": sum(costs) / total,
        "latency_avg_ms": sum(latencies) / total,
    }
