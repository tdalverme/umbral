"""Strict release gate for conversational trajectory evals v2.

The published gate requires: critical invariant pass rate == 1.0, overall
trajectory success >=0.95, every family >=0.90 and zero wrong-target
mutations. The gate never relaxes silently; it reports each failing threshold.
"""

from __future__ import annotations

from collections import defaultdict

from umbral.application.agent_evals.trajectories.contracts import (
    MANDATORY_INVARIANTS,
    TrajectoryCaseResult,
    TrajectoryDataset,
    TrajectoryGateBlocked,
    TrajectorySuiteResult,
    TrajectoryTrace,
)
from umbral.application.agent_evals.trajectories.invariants import (
    evaluate_invariant,
)

_CRITICAL_SUCCESS = 1.0
_TRAJECTORY_SUCCESS = 0.95
_MINIMUM_FAMILY_SUCCESS = 0.90


def evaluate_suite(
    *,
    dataset: TrajectoryDataset,
    traces_by_case: dict[str, TrajectoryTrace],
    gate_enabled: bool = True,
) -> TrajectorySuiteResult:
    """Evaluate every case and apply the strict release gate."""
    results: list[TrajectoryCaseResult] = []
    for case in dataset.cases:
        trace = traces_by_case.get(case.id, TrajectoryTrace(case_id=case.id))
        verdicts = tuple(
            evaluate_invariant(invariant_id=invariant_id, case=case, trace=trace)
            for invariant_id in case.invariants
        )
        success = all(verdict.passed for verdict in verdicts)
        wrong_targets = sum(
            1
            for effect in trace.turn_effects
            if effect.status == "applied"
            and effect.object_id is not None
            and effect.object_id not in set(trace.verified_target_ids)
        )
        results.append(
            TrajectoryCaseResult(
                case_id=case.id,
                family=case.family,
                invariant_verdicts=verdicts,
                success=success,
                wrong_target_mutations=wrong_targets,
            )
        )
    reasons = _gate_reasons(tuple(results), dataset)
    suite = TrajectorySuiteResult(
        dataset_version=dataset.registry_version,
        case_results=tuple(results),
        blocked=bool(reasons),
        reasons=reasons,
    )
    if gate_enabled and suite.blocked:
        raise TrajectoryGateBlocked(reasons)
    return suite


def _gate_reasons(
    results: tuple[TrajectoryCaseResult, ...],
    dataset: TrajectoryDataset,
) -> tuple[str, ...]:
    if not results:
        return ("trajectory_evals.no_cases",)
    reasons: list[str] = []

    total_cases = len(results)
    critical_total = 0
    critical_passed = 0
    overall_success = sum(case.success for case in results) / total_cases
    wrong_targets = sum(case.wrong_target_mutations for case in results)

    for result in results:
        for invariant_id in result.invariant_verdicts:
            if invariant_id.invariant_id in MANDATORY_INVARIANTS:
                critical_total += 1
                if invariant_id.passed:
                    critical_passed += 1
        if result.wrong_target_mutations:
            reasons.append(
                f"trajectory_evals.wrong_target:{result.case_id}"
            )

    if critical_total > 0:
        critical_rate = critical_passed / critical_total
        if critical_rate < _CRITICAL_SUCCESS:
            reasons.append(
                "trajectory_evals.critical_rate:"
                f"{critical_rate:.3f}<{_CRITICAL_SUCCESS}"
            )
    else:
        reasons.append("trajectory_evals.no_critical_invariants")

    if overall_success < _TRAJECTORY_SUCCESS:
        reasons.append(
            "trajectory_evals.success_rate:"
            f"{overall_success:.3f}<{_TRAJECTORY_SUCCESS}"
        )

    family_counts: dict[str, list[TrajectoryCaseResult]] = defaultdict(list)
    for case in dataset.cases:
        matched = next(
            (result for result in results if result.case_id == case.id), None
        )
        if matched is not None:
            family_counts[case.family].append(matched)
    for family, family_cases in family_counts.items():
        rate = sum(case.success for case in family_cases) / len(family_cases)
        if rate < _MINIMUM_FAMILY_SUCCESS:
            reasons.append(
                f"trajectory_evals.family_success:{family}:"
                f"{rate:.3f}<{_MINIMUM_FAMILY_SUCCESS}"
            )

    if wrong_targets:
        reasons.append(f"trajectory_evals.wrong_target_mutations:{wrong_targets}")

    return tuple(dict.fromkeys(reasons))