"""Sequential v3 suite runner with budget reservation and fresh-trial retry.

The runner is pure orchestration over ports: it never touches a gateway, a
database or a graph node. Trials run sequentially on purpose; concurrency is
intentionally not added until runtime evidence shows it is safe with the
Postgres checkpointer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from umbral.application.agent.ports import ModelGateway
from umbral.application.agent_evals.contracts import PriceTable
from umbral.application.agent_evals.price import case_cost
from umbral.application.agent_evals.v3.contracts import (
    CaseAggregate,
    EvalBudget,
    EvalCase,
    EvalDataset,
    EvalPolicy,
    EvalRelease,
    FailureKind,
    Fidelity,
    SuiteRun,
    TrialResult,
    TrialTrace,
)
from umbral.application.agent_evals.v3.grading import grade_trial
from umbral.application.agent_evals.v3.statistics import wilson_interval


class EvalModelAdapter(Protocol):
    """Model seam at the runner boundary; the Task 4 adapters implement it."""

    fidelity: Fidelity

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway: ...


class TrialExecutor(Protocol):
    """One trial through a real infrastructure stack, producing a trace."""

    def execute(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        model_adapter: EvalModelAdapter,
        trial_index: int,
        attempt_index: int,
    ) -> TrialTrace: ...


def run_suite(
    *,
    dataset: EvalDataset,
    release: EvalRelease,
    model_adapter: EvalModelAdapter,
    executor: TrialExecutor,
    policy: EvalPolicy,
    budget: EvalBudget,
    include_holdout: bool,
    price_table: PriceTable,
) -> SuiteRun:
    selected = [
        case
        for case in dataset.cases
        if include_holdout or case.partition != "holdout"
    ]
    results: list[TrialResult] = []
    failures: list[FailureKind] = []
    remaining_usd = budget.cap_usd
    total_cost_usd = 0.0
    total_latency_ms = 0
    complete = True

    for case in selected:
        trial_count = _trials_per_case(model_adapter.fidelity, case.risk, policy)
        for trial_index in range(trial_count):
            if (
                model_adapter.fidelity == "managed"
                and remaining_usd < policy.max_reserved_cost_per_trial_usd
            ):
                _append_unique(failures, "budget_exhausted")
                complete = False
                break
            attempt_index = 0
            while True:
                trace = executor.execute(
                    case=case,
                    release=release,
                    model_adapter=model_adapter,
                    trial_index=trial_index,
                    attempt_index=attempt_index,
                )
                result = _costed_result(case, trace, price_table)
                results.append(result)
                remaining_usd -= result.cost_usd
                total_cost_usd += result.cost_usd
                total_latency_ms += trace.latency_ms
                if (
                    result.failure_kind == "provider_failure"
                    and attempt_index < policy.provider_retry_limit
                ):
                    attempt_index += 1
                    continue
                if result.failure_kind == "provider_failure":
                    complete = False
                break
        else:
            continue
        break

    for result in results:
        if result.failure_kind is not None:
            _append_unique(failures, result.failure_kind)

    return SuiteRun(
        dataset_version=dataset.registry_version,
        policy_version=policy.registry_version,
        release_id=release.id,
        fidelity=model_adapter.fidelity,
        include_holdout=include_holdout,
        complete=complete,
        trial_results=tuple(results),
        case_aggregates=_aggregate_cases(results, selected, policy),
        failures=tuple(failures),
        total_cost_usd=total_cost_usd,
        total_latency_ms=total_latency_ms,
    )


def _trials_per_case(fidelity: Fidelity, risk: str, policy: EvalPolicy) -> int:
    if fidelity == "scripted":
        return policy.scripted_trials
    if risk == "critical":
        return policy.managed_critical_trials
    return policy.managed_normal_trials


def _costed_result(case: EvalCase, trace: TrialTrace, table: PriceTable) -> TrialResult:
    graded = grade_trial(case, trace)
    return replace(graded, cost_usd=case_cost(trace.model_calls, table))


def _aggregate_cases(
    results: list[TrialResult],
    cases: list[EvalCase],
    policy: EvalPolicy,
) -> tuple[CaseAggregate, ...]:
    by_id = {case.id: case for case in cases}
    grouped: dict[str, list[TrialResult]] = {}
    for result in results:
        grouped.setdefault(result.case_id, []).append(result)
    aggregates: list[CaseAggregate] = []
    for case_id in sorted(grouped):
        trials = tuple(grouped[case_id])
        case = by_id[case_id]
        successes = sum(1 for trial in trials if trial.failure_kind is None)
        trial_count = len(trials)
        aggregates.append(
            CaseAggregate(
                case_id=case_id,
                family=case.family,
                suite=case.suite,
                risk=case.risk,
                successes=successes,
                trials=trial_count,
                success_rate=successes / trial_count,
                all_trials_succeeded=successes == trial_count,
                interval=wilson_interval(
                    successes, trial_count, policy.confidence_level
                ),
                safety_violations=_count(trials, "safety_violation"),
                provider_failures=_count(trials, "provider_failure"),
                product_failures=_count(trials, "product_failure"),
                average_cost_usd=sum(trial.cost_usd for trial in trials) / trial_count,
                average_latency_ms=round(
                    sum(trial.trace.latency_ms for trial in trials) / trial_count
                ),
            )
        )
    return tuple(aggregates)


def _count(trials: tuple[TrialResult, ...], kind: FailureKind) -> int:
    return sum(1 for trial in trials if trial.failure_kind == kind)


def _append_unique(failures: list[FailureKind], kind: FailureKind) -> None:
    if kind not in failures:
        failures.append(kind)