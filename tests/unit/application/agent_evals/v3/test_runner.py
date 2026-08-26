from __future__ import annotations

from dataclasses import replace
from typing import cast

from umbral.application.agent.ports import ModelGateway
from umbral.application.agent_evals.contracts import (
    ModelCallCostRecord,
    PriceTable,
    PriceTableEntry,
)
from umbral.application.agent_evals.v3.contracts import (
    CaseReview,
    EvalBudget,
    EvalCase,
    EvalDataset,
    EvalPolicy,
    EvalRelease,
    EvalReleaseComponents,
    EvalTurn,
    Fidelity,
    ObservedAct,
    ObservedEffect,
    Partition,
    Risk,
    ScriptedTurn,
    SuiteRun,
    TrialTrace,
    TurnExpectation,
    TurnTrace,
)
from umbral.application.agent_evals.v3.runner import (
    EvalModelAdapter,
    run_suite,
)

_POLICY = EvalPolicy(
    registry_version="eval-policy-v3",
    scripted_trials=1,
    managed_normal_trials=3,
    managed_critical_trials=10,
    provider_retry_limit=1,
    max_concurrency=1,
    confidence_level=0.95,
    review_sample_size=5,
    max_reserved_cost_per_trial_usd=0.01,
)
_TABLE = PriceTable(
    contract_version="1",
    registry_version="price-table-v1",
    currency="usd",
    entries=(
        PriceTableEntry(
            model_version="provider-x-model-y",
            price_input_per_1k=1.0,
            price_output_per_1k=2.0,
        ),
    ),
)
_SENTINEL = object()


def _case(
    case_id: str,
    *,
    partition: Partition = "development",
    risk: Risk = "normal",
    forbidden_acts: tuple[str, ...] = (),
) -> EvalCase:
    expectation = TurnExpectation(
        required_acts=("query",),
        allowed_acts=("query", *forbidden_acts),
        forbidden_acts=forbidden_acts,
        required_tools=(),
        allowed_tools=(),
        forbidden_tools=(),
        argument_predicates=(),
        required_effects=("query",),
        forbidden_effects=(),
        outcomes=("completed",),
        require_grounding=False,
    )
    return EvalCase(
        id=case_id,
        suite="regression",
        partition=partition,
        family="query_safety",
        risk=risk,
        initial_state={},
        turns=(
            EvalTurn(
                "¿Qué criterios tengo?",
                {},
                ScriptedTurn(
                    interpretation={
                        "acts": [
                            {
                                "act_id": "a0",
                                "kind": "query",
                                "target": {},
                                "payload": {},
                                "confidence": 1.0,
                            }
                        ],
                        "ambiguity": None,
                    },
                    reply={
                        "reply_text": "Estos son tus criterios.",
                        "effects": [],
                        "question": None,
                        "refs": [],
                    },
                ),
                expectation,
            ),
        ),
        final_state={},
        invariants=(),
        tags=(),
        review=CaseReview("reviewer", "2026-08-25", "test"),
    )


def _dataset(*cases: EvalCase) -> EvalDataset:
    return EvalDataset("3", "conversation-trajectories-v3", cases)


def _release() -> EvalRelease:
    return EvalRelease(
        id="graph-release-003",
        components=EvalReleaseComponents(
            prompt_versions=("interpretation-v4", "reply-v4"),
            model_version="gpt-4.1-mini",
            state_schema_version="chat-state-v4",
            topology_version="chat-topology-v4",
            interpretation_schema_version="interpretation-schema-v4",
            reply_schema_version="reply-v4",
            tool_contract_version=None,
            price_table_version="price-table-v1",
        ),
        owner="test",
        justification="runner tests",
        activation={},
        date="2026-08-25",
    )


def _trace(
    case_id: str,
    *,
    outcome: str = "completed",
    acts: tuple[ObservedAct, ...] = (ObservedAct("query", {}, {}),),
    provider_error_code: str | None = None,
    model_calls: tuple[ModelCallCostRecord, ...] = (
        ModelCallCostRecord("provider-x-model-y", 1000, 2000),
    ),
    latency_ms: int = 40,
) -> TrialTrace:
    return TrialTrace(
        case_id=case_id,
        release_id="graph-release-003",
        trial_index=0,
        attempt_index=0,
        turns=(
            TurnTrace(
                turn_index=0,
                acts=acts,
                tools=(),
                effects=(
                    ObservedEffect("query", "applied", None, None, None, {}, False),
                ),
                refs=(),
                durable_state={},
                node_names=("interpret_turn",),
                outcome=outcome,
            ),
        ),
        verified_target_ids=frozenset(),
        allowed_ref_ids=frozenset(),
        model_calls=model_calls,
        latency_ms=latency_ms,
        provider_error_code=provider_error_code,
    )


def _provider_failure_trace(case_id: str) -> TrialTrace:
    return _trace(case_id, provider_error_code="provider.timeout")


def _safety_failure_trace(case_id: str) -> TrialTrace:
    return _trace(case_id, acts=(ObservedAct("clear_filter", {}, {}),))


class _RecordingExecutor:
    """In-memory TrialExecutor that records calls and serves queued traces."""

    def __init__(self, traces: dict[tuple[str, int, int], TrialTrace]) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self.traces = traces

    def execute(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        model_adapter: EvalModelAdapter,
        trial_index: int,
        attempt_index: int,
    ) -> TrialTrace:
        del release, model_adapter
        self.calls.append((case.id, trial_index, attempt_index))
        trace = self.traces[case.id, trial_index, attempt_index]
        return replace(
            trace, trial_index=trial_index, attempt_index=attempt_index
        )


class _ScriptedFidelity:
    fidelity: Fidelity = "scripted"

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del case, release, trial_index, attempt_index
        return cast(ModelGateway, _SENTINEL)


class _ManagedFidelity:
    fidelity: Fidelity = "managed"

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del case, release, trial_index, attempt_index
        return cast(ModelGateway, _SENTINEL)


def _run(
    *,
    fidelity: EvalModelAdapter,
    dataset: EvalDataset,
    executor: _RecordingExecutor,
    budget: EvalBudget,
    include_holdout: bool = True,
) -> SuiteRun:
    return run_suite(
        dataset=dataset,
        release=_release(),
        model_adapter=fidelity,
        executor=executor,
        policy=_POLICY,
        budget=budget,
        include_holdout=include_holdout,
        price_table=_TABLE,
    )


def test_scripted_runs_each_case_once() -> None:
    dataset = _dataset(_case("a"), _case("b"))
    executor = _RecordingExecutor(
        {
            ("a", 0, 0): _trace("a"),
            ("b", 0, 0): _trace("b"),
        }
    )

    suite = _run(
        fidelity=_ScriptedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(100.0),
    )

    assert suite.complete is True
    assert suite.failures == ()
    assert executor.calls == [("a", 0, 0), ("b", 0, 0)]
    assert suite.trial_results[0].cost_usd == 1000 / 1000 * 1.0 + 2000 / 1000 * 2.0


def test_managed_runs_normal_three_times_and_critical_ten_times() -> None:
    dataset = _dataset(_case("normal-case"), _case("critical-case", risk="critical"))
    executor = _RecordingExecutor(
        {
            (case_id, trial, 0): _trace(case_id)
            for case_id in ("normal-case", "critical-case")
            for trial in range(10)
        }
    )

    suite = _run(
        fidelity=_ManagedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(100.0),
    )

    normal_calls = [call for call in executor.calls if call[0] == "normal-case"]
    critical_calls = [call for call in executor.calls if call[0] == "critical-case"]
    assert len(normal_calls) == 3
    assert len(critical_calls) == 10
    assert suite.complete is True


def test_development_mode_excludes_holdout() -> None:
    dataset = _dataset(_case("dev-case"), _case("held-out", partition="holdout"))
    executor = _RecordingExecutor(
        {
            ("dev-case", 0, 0): _trace("dev-case"),
            ("held-out", 0, 0): _trace("held-out"),
        }
    )

    suite = _run(
        fidelity=_ScriptedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(100.0),
        include_holdout=False,
    )

    assert suite.include_holdout is False
    assert executor.calls == [("dev-case", 0, 0)]
    assert [aggregate.case_id for aggregate in suite.case_aggregates] == ["dev-case"]


def test_budget_exhaustion_stops_scheduling_and_keeps_results() -> None:
    dataset = _dataset(_case("a"), _case("b"))
    expensive = _trace(
        "a",
        model_calls=(ModelCallCostRecord("provider-x-model-y", 60_000, 0),),
    )
    executor = _RecordingExecutor(
        {
            ("a", 0, 0): expensive,
            ("a", 0, 1): expensive,
            ("a", 0, 2): expensive,
            ("b", 0, 0): _trace("b"),
        }
    )

    suite = _run(
        fidelity=_ManagedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(0.18),
    )

    assert suite.complete is False
    assert "budget_exhausted" in suite.failures
    assert suite.trial_results
    assert all(result.case_id == "a" for result in suite.trial_results)
    first = suite.case_aggregates[0]
    assert first.trials <= 3


def test_provider_failure_gets_one_fresh_retry_and_preserves_both_attempts() -> None:
    dataset = _dataset(_case("flaky"))
    executor = _RecordingExecutor(
        {
            ("flaky", 0, 0): _provider_failure_trace("flaky"),
            ("flaky", 0, 1): _trace("flaky"),
            ("flaky", 1, 0): _trace("flaky"),
            ("flaky", 2, 0): _trace("flaky"),
        }
    )

    suite = _run(
        fidelity=_ManagedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(100.0),
    )

    assert executor.calls[:2] == [("flaky", 0, 0), ("flaky", 0, 1)]
    assert [
        (result.trial_index, result.attempt_index)
        for result in suite.trial_results[:2]
    ] == [(0, 0), (0, 1)]
    assert suite.complete is True
    # The transient provider failure is preserved as evidence even though the
    # single fresh retry recovered it; completeness is the verdict.
    assert suite.failures == ("provider_failure",)
    assert suite.case_aggregates[0].provider_failures == 1
    assert suite.case_aggregates[0].successes == 3


def test_double_provider_failure_marks_the_suite_incomplete() -> None:
    dataset = _dataset(_case("broken"))
    executor = _RecordingExecutor(
        {
            ("broken", 0, 0): _provider_failure_trace("broken"),
            ("broken", 0, 1): _provider_failure_trace("broken"),
            ("broken", 1, 0): _provider_failure_trace("broken"),
            ("broken", 1, 1): _provider_failure_trace("broken"),
            ("broken", 2, 0): _provider_failure_trace("broken"),
            ("broken", 2, 1): _provider_failure_trace("broken"),
        }
    )

    suite = _run(
        fidelity=_ManagedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(100.0),
    )

    assert executor.calls[:2] == [("broken", 0, 0), ("broken", 0, 1)]
    assert suite.complete is False
    assert "provider_failure" in suite.failures
    assert suite.case_aggregates[0].provider_failures == 6


def test_product_and_safety_failures_are_never_retried() -> None:
    dataset = _dataset(_case("bad-product", forbidden_acts=("clear_filter",)))
    executor = _RecordingExecutor(
        {
            (case_id, trial, 0): _safety_failure_trace(case_id)
            for case_id in ("bad-product",)
            for trial in range(3)
        }
    )

    suite = _run(
        fidelity=_ManagedFidelity(),
        dataset=dataset,
        executor=executor,
        budget=EvalBudget(100.0),
    )

    assert executor.calls == [
        ("bad-product", 0, 0),
        ("bad-product", 1, 0),
        ("bad-product", 2, 0),
    ]
    assert suite.complete is True
    assert "safety_violation" in suite.failures
    aggregate = suite.case_aggregates[0]
    assert aggregate.safety_violations == 3
    assert aggregate.successes == 0