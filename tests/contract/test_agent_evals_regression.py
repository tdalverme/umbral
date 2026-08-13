"""Conformance of the regression gate over the published contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from umbral.application.agent_evals.contracts import (
    AgentEvalsBlocked,
    CaseEvalResult,
    GoldenDataset,
)
from umbral.application.agent_evals.golden import load_golden_dataset
from umbral.application.agent_evals.regression import run_regression
from umbral.application.agent_evals.releases import load_releases

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "conversations-golden-v1.json"
RELEASES_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "graph-releases-v1.json"


def _results_from_expectations(
    dataset: GoldenDataset, *, tamper_case_id: str | None = None
) -> list[CaseEvalResult]:
    results: list[CaseEvalResult] = []
    for case in dataset.cases:
        recorded_ok = case.expectation.outcome in {"completed"}
        results.append(
            CaseEvalResult(
                case_id=case.id,
                tool_selection_ok=not (tamper_case_id == case.id),
                args_valid=True,
                grounding_ok=True,
                confirmation_ok=True,
                outcome_ok=recorded_ok,
                cost_usd=0.01,
                latency_ms=10,
                verdict="ok",
            )
        )
    return results


def test_baseline_vs_itself_passes_over_the_published_dataset() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    releases = load_releases(
        RELEASES_PATH,
        known_case_ids=frozenset({case.id for case in dataset.cases}),
    )
    release = releases.active_release()
    assert release is not None
    results = _results_from_expectations(dataset)
    report = run_regression(
        dataset=dataset,
        baseline_results=results,
        candidate_results=results,
        baseline_release=release,
        candidate_release=release,
        declared_cases=frozenset(),
        cost_threshold_pct=20.0,
        latency_threshold_ms=1500,
    )
    assert report.blocked is False
    assert len(report.case_results) == len(dataset.cases)


def test_tampered_candidate_blocks_unless_declared() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    releases = load_releases(
        RELEASES_PATH,
        known_case_ids=frozenset({case.id for case in dataset.cases}),
    )
    release = releases.active_release()
    assert release is not None
    baseline = _results_from_expectations(dataset)
    candidate = _results_from_expectations(dataset, tamper_case_id="conversation-001")
    with pytest.raises(AgentEvalsBlocked) as excinfo:
        run_regression(
            dataset=dataset,
            baseline_results=baseline,
            candidate_results=candidate,
            baseline_release=release,
            candidate_release=release,
            declared_cases=frozenset(),
            cost_threshold_pct=20.0,
            latency_threshold_ms=1500,
        )
    assert any(
        "agent_evals.tool_selection_change" in reason
        for reason in excinfo.value.reasons
    )
    report = run_regression(
        dataset=dataset,
        baseline_results=baseline,
        candidate_results=candidate,
        baseline_release=release,
        candidate_release=release,
        declared_cases=frozenset({"conversation-001"}),
        cost_threshold_pct=20.0,
        latency_threshold_ms=1500,
    )
    assert report.blocked is False
