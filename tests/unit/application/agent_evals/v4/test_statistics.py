"""Unit tests for V4 eval statistics (exact unrounded values)."""

from __future__ import annotations

from umbral.application.agent_evals.v4.contracts import (
    TrialEvidenceV4,
    TurnEvidenceV4,
)
from umbral.application.agent_evals.v4.statistics import (
    cost_summary_usd,
    latency_percentiles_ms,
    median_success_per_family,
    wilson_interval_per_case,
)

RELEASE = "graph-release-005"


def _turn() -> TurnEvidenceV4:
    return TurnEvidenceV4(
        message="hola",
        authorized_context={},
        interpretation=None,
        schema_valid=True,
        policy_input=None,
        plan=None,
        effects=(),
        state_before={},
        state_after={},
        reply_text="",
        failure_stage=None,
        reason_codes=(),
    )


def _trial(case_id: str, *, ok: bool) -> TrialEvidenceV4:
    return TrialEvidenceV4(
        case_id=case_id,
        release_id=RELEASE,
        trial_index=0,
        turns=(_turn(),),
        safety_ok=ok,
        quality_ok=ok,
        cost_usd=0.01,
        latency_ms=10,
    )


def test_median_success_per_family_is_exact() -> None:
    trials = (
        _trial("a", ok=True),
        _trial("a", ok=True),
        _trial("a", ok=False),
        _trial("b", ok=True),
    )

    summary = median_success_per_family(trials)

    by_family = {item.family: item for item in summary}
    assert by_family["a"].median_success_rate == 1.0
    assert by_family["a"].range_min_success_rate == 0.0
    assert by_family["a"].range_max_success_rate == 1.0
    assert by_family["b"].median_success_rate == 1.0


def test_wilson_interval_per_case_matches_exact_counts() -> None:
    trials = tuple(_trial("a", ok=True) for _ in range(5))
    trials += (_trial("a", ok=False),)

    intervals = wilson_interval_per_case(trials)

    assert intervals[0].case_id == "a"
    assert intervals[0].successes == 5
    assert intervals[0].trials == 6
    assert intervals[0].lower < intervals[0].upper


def test_latency_percentiles_p50_p95() -> None:
    summary = latency_percentiles_ms([100, 200, 300, 400, 5000])

    assert summary.p50_ms == 300
    assert summary.p95_ms == 5000


def test_cost_summary_totals_and_averages() -> None:
    summary = cost_summary_usd([0.01, 0.02, 0.03])

    assert summary.total_usd == 0.06
    assert summary.average_per_trial_usd == 0.02


def test_empty_inputs_yield_zero_summaries() -> None:
    assert median_success_per_family(()) == ()
    assert latency_percentiles_ms([]).p50_ms == 0
    assert cost_summary_usd([]).total_usd == 0.0