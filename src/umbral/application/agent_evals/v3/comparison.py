"""Baseline/candidate comparison and the bounded review queue (v3).

Comparison only consumes graded aggregates: it never inspects raw model
text. Compatibility is decided by the published release/dataset/policy key;
model and prompt versions are intentionally not part of it because those are
the variables being compared.
"""

from __future__ import annotations

from umbral.application.agent_evals.v3.contracts import (
    CaseAggregate,
    CaseDelta,
    ComparisonReport,
    EvalDataset,
    EvalPolicy,
    EvalRelease,
    EvalV3ValidationError,
    ReviewItem,
    SuiteRun,
)
from umbral.application.agent_evals.v3.releases import release_compatibility_key


def compare_runs(
    *,
    baseline: SuiteRun,
    candidate: SuiteRun,
    baseline_release: EvalRelease,
    candidate_release: EvalRelease,
    dataset: EvalDataset,
    policy: EvalPolicy,
) -> ComparisonReport:
    _assert_compatible(
        baseline=baseline,
        candidate=candidate,
        baseline_release=baseline_release,
        candidate_release=candidate_release,
        dataset=dataset,
        policy=policy,
    )

    baseline_by_id = {
        aggregate.case_id: aggregate for aggregate in baseline.case_aggregates
    }
    candidate_by_id = {
        aggregate.case_id: aggregate for aggregate in candidate.case_aggregates
    }
    case_ids = sorted(set(baseline_by_id) | set(candidate_by_id))

    deltas = tuple(
        _delta(
            baseline_by_id.get(case_id),
            candidate_by_id.get(case_id),
        )
        for case_id in case_ids
    )
    blocked, block_reasons = _blocked_verdict(candidate)
    approvable = baseline.complete and candidate.complete and not blocked
    reasons: list[str] = []
    if not baseline.complete:
        reasons.append("baseline_incomplete")
    if not candidate.complete:
        reasons.append("candidate_incomplete")
    reasons.extend(block_reasons)
    return ComparisonReport(
        baseline=baseline,
        candidate=candidate,
        deltas=deltas,
        review_items=_review_queue(candidate, deltas, policy),
        blocked=blocked,
        approvable=approvable,
        reasons=tuple(reasons),
    )


def _assert_compatible(
    *,
    baseline: SuiteRun,
    candidate: SuiteRun,
    baseline_release: EvalRelease,
    candidate_release: EvalRelease,
    dataset: EvalDataset,
    policy: EvalPolicy,
) -> None:
    errors: list[str] = []
    if baseline.release_id != baseline_release.id:
        errors.append(f"agent_evals_v3.release_mismatch:{baseline.release_id}")
    if candidate.release_id != candidate_release.id:
        errors.append(f"agent_evals_v3.release_mismatch:{candidate.release_id}")
    baseline_key = release_compatibility_key(baseline_release, dataset, policy)
    candidate_key = release_compatibility_key(candidate_release, dataset, policy)
    if baseline_key != candidate_key:
        errors.append(
            "agent_evals_v3.incompatible_releases:"
            + "|".join(
                f"{left}={right}"
                for left, right in zip(baseline_key, candidate_key, strict=True)
            )
        )
    if errors:
        raise EvalV3ValidationError(tuple(errors))


def _delta(
    baseline: CaseAggregate | None, candidate: CaseAggregate | None
) -> CaseDelta:
    if candidate is not None:
        identity = candidate
    else:
        assert baseline is not None
        identity = baseline
    base_successes = baseline.successes if baseline is not None else 0
    base_trials = baseline.trials if baseline is not None else 0
    cand_successes = candidate.successes if candidate is not None else 0
    cand_trials = candidate.trials if candidate is not None else 0
    base_rate = base_successes / base_trials if base_trials else 0.0
    cand_rate = cand_successes / cand_trials if cand_trials else 0.0
    return CaseDelta(
        case_id=identity.case_id,
        baseline_successes=base_successes,
        baseline_trials=base_trials,
        candidate_successes=cand_successes,
        candidate_trials=cand_trials,
        success_rate_delta=cand_rate - base_rate,
        consistency_changed=(
            (baseline.all_trials_succeeded if baseline is not None else False)
            != (candidate.all_trials_succeeded if candidate is not None else False)
        ),
        cost_delta_usd=(
            (candidate.average_cost_usd if candidate is not None else 0.0)
            - (baseline.average_cost_usd if baseline is not None else 0.0)
        ),
        latency_delta_ms=(
            (candidate.average_latency_ms if candidate is not None else 0)
            - (baseline.average_latency_ms if baseline is not None else 0)
        ),
        regressed=cand_trials > 0 and cand_rate < base_rate,
    )


def _blocked_verdict(candidate: SuiteRun) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    seen_safety: set[str] = set()
    seen_contract: set[str] = set()
    for result in candidate.trial_results:
        if (
            result.failure_kind == "safety_violation"
            and result.case_id not in seen_safety
        ):
            seen_safety.add(result.case_id)
            reasons.append(f"safety:{result.case_id}")
        elif (
            result.failure_kind == "harness_failure"
            and result.case_id not in seen_contract
        ):
            seen_contract.add(result.case_id)
            reasons.append(f"contract:{result.case_id}")
    return bool(reasons), reasons


def _review_queue(
    candidate: SuiteRun,
    deltas: tuple[CaseDelta, ...],
    policy: EvalPolicy,
) -> tuple[ReviewItem, ...]:
    items: list[ReviewItem] = []
    sampled: set[str] = set()

    safety_ids = _cases_with(candidate, "safety_violation")
    for case_id in sorted(safety_ids):
        items.append(
            ReviewItem(case_id, "safety", _trial_indexes(candidate, case_id))
        )
        sampled.add(case_id)

    regression_deltas = [delta for delta in deltas if delta.regressed]
    regression_deltas.sort(
        key=lambda delta: (
            delta.success_rate_delta,  # largest drop (most negative) first
            delta.case_id,
        )
    )
    for delta in regression_deltas:
        if delta.case_id in sampled:
            continue
        items.append(
            ReviewItem(
                delta.case_id,
                "regression",
                _trial_indexes(candidate, delta.case_id),
            )
        )
        sampled.add(delta.case_id)

    for case_id in _additional_sample(candidate, sampled, policy.review_sample_size):
        items.append(ReviewItem(case_id, "sample", _trial_indexes(candidate, case_id)))
    return tuple(items)


def _additional_sample(
    candidate: SuiteRun, sampled: set[str], sample_size: int
) -> list[str]:
    if sample_size <= 0:
        return []
    remaining = sorted(
        (
            aggregate
            for aggregate in candidate.case_aggregates
            if aggregate.case_id not in sampled
        ),
        key=lambda item: (item.family, item.case_id),
    )
    chosen: list[str] = []
    families: set[str] = set()
    for aggregate in sorted(remaining, key=lambda item: (item.family, item.case_id)):
        if aggregate.family in families:
            continue
        families.add(aggregate.family)
        chosen.append(aggregate.case_id)
        if len(chosen) == sample_size:
            return chosen
    for aggregate in sorted(remaining, key=lambda item: item.case_id):
        if aggregate.case_id in chosen:
            continue
        chosen.append(aggregate.case_id)
        if len(chosen) == sample_size:
            break
    return chosen


def _cases_with(candidate: SuiteRun, kind: str) -> set[str]:
    return {
        result.case_id
        for result in candidate.trial_results
        if result.failure_kind == kind
    }


def _trial_indexes(candidate: SuiteRun, case_id: str) -> tuple[int, ...]:
    indexes = sorted(
        {
            result.trial_index
            for result in candidate.trial_results
            if result.case_id == case_id
        }
    )
    return tuple(indexes)