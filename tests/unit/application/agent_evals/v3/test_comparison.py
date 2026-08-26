from __future__ import annotations

import pytest

from umbral.application.agent_evals.v3.comparison import compare_runs
from umbral.application.agent_evals.v3.contracts import (
    CaseAggregate,
    CaseReview,
    ComparisonReport,
    EvalCase,
    EvalDataset,
    EvalPolicy,
    EvalRelease,
    EvalReleaseComponents,
    EvalTurn,
    EvalV3ValidationError,
    Interval,
    ScriptedTurn,
    SuiteRun,
    TrialResult,
    TrialTrace,
    TurnExpectation,
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


def _dataset_case() -> EvalCase:
    expectation = TurnExpectation((), (), (), (), (), (), (), (), (), (), False)
    return EvalCase(
        id="query-case",
        suite="regression",
        partition="development",
        family="query_safety",
        risk="normal",
        initial_state={},
        turns=(EvalTurn("hi", {}, ScriptedTurn({}, {}), expectation),),
        final_state={},
        invariants=(),
        tags=(),
        review=CaseReview("reviewer", "2026-08-25", "test"),
    )


_DATASET = EvalDataset(
    "3", "conversation-trajectories-v3", (_dataset_case(),)
)


def _release(
    *,
    release_id: str = "graph-release-003",
    model_version: str = "gpt-4.1-mini",
    reply_schema_version: str = "reply-v4",
) -> EvalRelease:
    return EvalRelease(
        id=release_id,
        components=EvalReleaseComponents(
            prompt_versions=("interpretation-v4", "reply-v4"),
            model_version=model_version,
            state_schema_version="chat-state-v4",
            topology_version="chat-topology-v4",
            interpretation_schema_version="interpretation-schema-v4",
            reply_schema_version=reply_schema_version,
            tool_contract_version=None,
            price_table_version="price-table-v1",
        ),
        owner="test",
        justification="comparison tests",
        activation={},
        date="2026-08-25",
    )


def _trace(case_id: str, trial_index: int) -> TrialTrace:
    return TrialTrace(
        case_id=case_id,
        release_id="graph-release-003",
        trial_index=trial_index,
        attempt_index=0,
        turns=(),
        verified_target_ids=frozenset(),
        allowed_ref_ids=frozenset(),
        model_calls=(),
        latency_ms=0,
    )


def _result(
    case_id: str, trial_index: int, kind: str | None = None
) -> TrialResult:
    return TrialResult(
        case_id=case_id,
        trial_index=trial_index,
        attempt_index=0,
        safety_ok=kind != "safety_violation",
        quality_ok=kind is None,
        failure_kind=kind,  # type: ignore[arg-type]
        checks=(),
        cost_usd=0.0,
        trace=_trace(case_id, trial_index),
    )


def _aggregate(
    case_id: str,
    family: str,
    *,
    successes: int,
    trials: int,
    safety_violations: int = 0,
    provider_failures: int = 0,
) -> CaseAggregate:
    return CaseAggregate(
        case_id=case_id,
        family=family,
        suite="regression",
        risk="normal",
        successes=successes,
        trials=trials,
        success_rate=successes / trials if trials else 0.0,
        all_trials_succeeded=successes == trials,
        interval=Interval(0.0, 1.0),
        safety_violations=safety_violations,
        provider_failures=provider_failures,
        product_failures=0,
        average_cost_usd=0.0,
        average_latency_ms=0,
    )


def _run(
    release_id: str,
    aggregates: list[CaseAggregate],
    results: list[TrialResult],
    *,
    complete: bool = True,
) -> SuiteRun:
    return SuiteRun(
        dataset_version="conversation-trajectories-v3",
        policy_version="eval-policy-v3",
        release_id=release_id,
        fidelity="scripted",
        include_holdout=True,
        complete=complete,
        trial_results=tuple(results),
        case_aggregates=tuple(aggregates),
        failures=(),
        total_cost_usd=0.0,
        total_latency_ms=0,
    )


def _compare(
    baseline: SuiteRun,
    candidate: SuiteRun,
    *,
    baseline_release: EvalRelease | None = None,
    candidate_release: EvalRelease | None = None,
) -> ComparisonReport:
    return compare_runs(
        baseline=baseline,
        candidate=candidate,
        baseline_release=baseline_release or _release(),
        candidate_release=candidate_release or _release(),
        dataset=_DATASET,
        policy=_POLICY,
    )


def _passing_run(
    case_id: str = "query-case",
    complete: bool = True,
    release_id: str = "graph-release-003",
) -> SuiteRun:
    return _run(
        release_id,
        [_aggregate(case_id, "query_safety", successes=1, trials=1)],
        [_result(case_id, 0)],
        complete=complete,
    )


def test_incompatible_release_keys_are_rejected_before_deltas() -> None:
    baseline = _run(
        "graph-release-003",
        [_aggregate("query-case", "query_safety", successes=1, trials=1)],
        [_result("query-case", 0)],
    )
    candidate = _run(
        "graph-release-004",
        [_aggregate("query-case", "query_safety", successes=1, trials=1)],
        [_result("query-case", 0)],
    )
    candidate_release = _release(
        release_id="graph-release-004", reply_schema_version="reply-v4b"
    )

    with pytest.raises(EvalV3ValidationError) as raised:
        _compare(baseline, candidate, candidate_release=candidate_release)

    assert raised.value.error_codes[0].startswith(
        "agent_evals_v3.incompatible_releases:"
    )


def test_model_and_prompt_changes_are_compatible() -> None:
    baseline = _passing_run()
    candidate = _passing_run(case_id="query-case", release_id="graph-release-004")
    candidate_release = _release(
        release_id="graph-release-004", model_version="gpt-5"
    )

    report = _compare(baseline, candidate, candidate_release=candidate_release)

    assert report.blocked is False
    assert report.approvable is True


def test_candidate_safety_violation_blocks_approval() -> None:
    baseline = _passing_run()
    candidate = _run(
        "graph-release-003",
        [
            _aggregate(
                "query-case",
                "query_safety",
                successes=0,
                trials=1,
                safety_violations=1,
            )
        ],
        [_result("query-case", 0, kind="safety_violation")],
    )

    report = _compare(baseline, candidate)

    assert report.blocked is True
    assert report.approvable is False
    assert any(reason.startswith("safety:") for reason in report.reasons)


def test_candidate_regression_is_reported_but_does_not_block() -> None:
    baseline = _run(
        "graph-release-003",
        [_aggregate("query-case", "query_safety", successes=5, trials=5)],
        [_result("query-case", i) for i in range(5)],
    )
    candidate = _run(
        "graph-release-003",
        [_aggregate("query-case", "query_safety", successes=3, trials=5)],
        [_result("query-case", i) for i in range(5)],
    )

    report = _compare(baseline, candidate)

    delta = report.deltas[0]
    assert delta.regressed is True
    assert delta.success_rate_delta == pytest.approx(-0.4)
    assert report.blocked is False
    assert report.approvable is True


def test_incomplete_suite_never_supports_approval() -> None:
    baseline = _run(
        "graph-release-003",
        [_aggregate("query-case", "query_safety", successes=0, trials=1)],
        [_result("query-case", 0, kind="provider_failure")],
        complete=False,
    )
    candidate = _passing_run()

    report = _compare(baseline, candidate)

    assert report.approvable is False
    assert "baseline_incomplete" in report.reasons


def test_review_queue_orders_safety_then_regression_drops_then_sample() -> None:
    family_map = {
        "c1": ("f1", 1, 1),
        "c2": ("f1", 2, 5),
        "c3": ("f2", 3, 5),
        "c4": ("f3", 1, 1),
        "c5": ("f3", 1, 1),
        "c6": ("f4", 1, 1),
        "c7": ("f5", 1, 1),
        "c8": ("f6", 1, 1),
    }
    baseline_aggs = [
        _aggregate(case_id, family, successes=5, trials=5)
        for case_id, (family, *_rest) in family_map.items()
    ]
    baseline_results = [
        _result(case_id, i) for case_id in family_map for i in range(5)
    ]
    candidate_aggs = [
        _aggregate(
            case_id,
            family,
            successes=(0 if case_id == "c1" else successes),
            trials=(2 if case_id == "c1" else trials),
            safety_violations=1 if case_id == "c1" else 0,
        )
        for case_id, (family, successes, trials) in family_map.items()
    ]
    candidate_results = [
        _result("c1", 0, kind="safety_violation"),
        _result("c1", 1, kind="safety_violation"),
    ] + [_result("c2", i) for i in range(5)] + [
        _result(case_id, i)
        for case_id in ("c3", "c4", "c5", "c6", "c7", "c8")
        for i in range(family_map[case_id][2])
    ]
    baseline = _run(
        "graph-release-003",
        baseline_aggs,
        baseline_results,
    )
    candidate = _run(
        "graph-release-003",
        candidate_aggs,
        candidate_results,
    )

    report = _compare(baseline, candidate)

    assert [
        (item.case_id, item.reason) for item in report.review_items
    ] == [
        ("c1", "safety"),
        ("c2", "regression"),
        ("c3", "regression"),
        ("c4", "sample"),
        ("c6", "sample"),
        ("c7", "sample"),
        ("c8", "sample"),
        ("c5", "sample"),
    ]
    assert report.review_items[0].trial_indexes == (0, 1)
    assert len(report.review_items) == 8
    assert all(
        item.reason in {"safety", "regression", "sample"}
        for item in report.review_items
    )


def test_sample_is_bounded_and_deterministic() -> None:
    aggregates = [
        _aggregate(f"case-{i}", f"family-{i}", successes=1, trials=1)
        for i in range(12)
    ]
    results = [_result(f"case-{i}", 0) for i in range(12)]
    baseline = _run("graph-release-003", aggregates, results)
    candidate = _run("graph-release-003", aggregates, results)

    report = _compare(baseline, candidate)
    second = _compare(baseline, candidate)

    assert len(report.review_items) == 5
    assert [item.case_id for item in report.review_items] == [
        item.case_id for item in second.review_items
    ]