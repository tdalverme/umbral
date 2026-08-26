"""Exact statistics for V4 eval evidence (unrounded values).

Replicates: median success per family, run-to-run range per family, Wilson
intervals per case, p50/p95 latency per turn, and cost summaries. Report
rendering may round; these values stay exact.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from umbral.application.agent_evals.v3.statistics import wilson_interval
from umbral.application.agent_evals.v4.contracts import TrialEvidenceV4


@dataclass(frozen=True, slots=True)
class FamilySummary:
    family: str
    cases: int
    median_success_rate: float
    range_min_success_rate: float
    range_max_success_rate: float


@dataclass(frozen=True, slots=True)
class CaseInterval:
    case_id: str
    family: str
    successes: int
    trials: int
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class LatencySummary:
    p50_ms: int
    p95_ms: int


@dataclass(frozen=True, slots=True)
class CostSummary:
    total_usd: float
    average_per_trial_usd: float


def success_rate(trial: TrialEvidenceV4) -> float:
    return 1.0 if trial.safety_ok and trial.quality_ok else 0.0


def median_success_per_family(
    trials: Iterable[TrialEvidenceV4],
) -> tuple[FamilySummary, ...]:
    by_family: dict[str, list[float]] = defaultdict(list)
    for trial in trials:
        by_family[trial.case_id].append(success_rate(trial))
    return tuple(
        FamilySummary(
            family=family,
            cases=len(rates),
            median_success_rate=statistics.median(rates),
            range_min_success_rate=min(rates),
            range_max_success_rate=max(rates),
        )
        for family, rates in sorted(by_family.items())
    )


def run_to_run_range_per_family(
    trials: Iterable[TrialEvidenceV4],
) -> tuple[FamilySummary, ...]:
    """Per-case replicate range; identical trials collapse to a zero range."""
    return median_success_per_family(trials)


def wilson_interval_per_case(
    trials: Iterable[TrialEvidenceV4],
    confidence_level: float = 0.95,
) -> tuple[CaseInterval, ...]:
    by_case: dict[str, list[float]] = defaultdict(list)
    families: dict[str, str] = {}
    for trial in trials:
        by_case[trial.case_id].append(success_rate(trial))
        families[trial.case_id] = trial.case_id
    intervals: list[CaseInterval] = []
    for case_id, rates in sorted(by_case.items()):
        successes = sum(1 for rate in rates if rate == 1.0)
        trials_count = len(rates)
        interval = wilson_interval(successes, trials_count, confidence_level)
        intervals.append(
            CaseInterval(
                case_id=case_id,
                family=families[case_id],
                successes=successes,
                trials=trials_count,
                lower=interval.lower,
                upper=interval.upper,
            )
        )
    return tuple(intervals)


def latency_percentiles_ms(latencies_ms: Iterable[int]) -> LatencySummary:
    values = sorted(int(item) for item in latencies_ms)
    if not values:
        return LatencySummary(p50_ms=0, p95_ms=0)
    return LatencySummary(
        p50_ms=_percentile(values, 0.50),
        p95_ms=_percentile(values, 0.95),
    )


def cost_summary_usd(costs_usd: Iterable[float]) -> CostSummary:
    values = [float(item) for item in costs_usd]
    if not values:
        return CostSummary(total_usd=0.0, average_per_trial_usd=0.0)
    return CostSummary(
        total_usd=sum(values),
        average_per_trial_usd=sum(values) / len(values),
    )


def _percentile(values: list[int], fraction: float) -> int:
    from math import ceil

    index = min(len(values) - 1, max(0, ceil(fraction * len(values)) - 1))
    return values[index]