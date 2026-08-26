# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""v3 flow orchestration tests over fake adapters/executors (no network)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from umbral.application.agent_evals.v3.contracts import (
    CaseAggregate,
    CaseReview,
    EvalCase,
    EvalDataset,
    EvalReleases,
    EvalTurn,
    Interval,
    ScriptedTurn,
    SuiteRun,
    TrialResult,
    TrialTrace,
    TurnExpectation,
)
from umbral.infrastructure.agent_evals import v3_flow

ROOT = Path(__file__).resolve().parents[4]
CONTRACTS = ROOT / "contracts" / "agent-evals"


def _settings(fake: object = None) -> object:
    return type(
        "Settings",
        (),
        {
            "agent_model_provider": "managed",
            "agent_managed_endpoint": "http://gateway:8080/",
            "agent_managed_api_key": "x",
            "agent_model_name": "provider-model",
            "agent_model_timeout_seconds": 30.0,
            "database_url": "postgresql://unused",
            "__fake__": fake,
        },
    )()


def _dataset() -> EvalDataset:
    expectation = TurnExpectation((), (), (), (), (), (), (), (), (), (), False)
    cases = tuple(
        EvalCase(
            id=f"case-{index}",
            suite="regression",
            partition="development",
            family=f"family-{index % 3}",
            risk="normal" if index % 2 else "critical",
            initial_state={},
            turns=(EvalTurn("hi", {}, ScriptedTurn({}, {}), expectation),),
            final_state={},
            invariants=(),
            tags=(),
            review=CaseReview("tomi", "2026-08-25", "test"),
        )
        for index in range(6)
    )
    return EvalDataset("3", "conversation-trajectories-v3", cases)


def _suite(release_id: str, *, mode: str) -> SuiteRun:
    dataset = _dataset()
    results: list[TrialResult] = []
    aggregates: list[CaseAggregate] = []
    for case in dataset.cases:
        kind: str | None = None
        if mode == "safety" and case.id == "case-0":
            kind = "safety_violation"
        if mode == "incomplete" and case.id == "case-0":
            kind = "provider_failure"
        results.append(
            TrialResult(
                case_id=case.id,
                trial_index=0,
                attempt_index=0,
                safety_ok=kind != "safety_violation",
                quality_ok=kind is None,
                failure_kind=kind,
                checks=(),
                cost_usd=0.01,
                trace=TrialTrace(
                    case_id=case.id,
                    release_id=release_id,
                    trial_index=0,
                    attempt_index=0,
                    turns=(),
                    verified_target_ids=frozenset(),
                    allowed_ref_ids=frozenset(),
                    model_calls=(),
                    latency_ms=50,
                ),
            )
        )
        aggregates.append(
            CaseAggregate(
                case_id=case.id,
                family=case.family,
                suite=case.suite,
                risk=case.risk,
                successes=0 if kind else 1,
                trials=1,
                success_rate=0.0 if kind else 1.0,
                all_trials_succeeded=kind is None,
                interval=Interval(0.0, 1.0),
                safety_violations=1 if kind == "safety_violation" else 0,
                provider_failures=1 if kind == "provider_failure" else 0,
                product_failures=0,
                average_cost_usd=0.01,
                average_latency_ms=50,
            )
        )
    return SuiteRun(
        dataset_version="conversation-trajectories-v3",
        policy_version="eval-policy-v3",
        release_id=release_id,
        fidelity="managed",
        include_holdout=True,
        complete=mode != "incomplete",
        trial_results=tuple(results),
        case_aggregates=tuple(aggregates),
        failures=(),
        total_cost_usd=0.06,
        total_latency_ms=300,
    )


def _run_flow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mode: str,
    baseline_id: str = "graph-release-003",
    candidate_id: str = "graph-release-004",
    provider: str = "managed",
) -> int:
    settings = _settings()
    if provider != "managed":
        settings = type(
            "Settings",
            (),
            {
                "agent_model_provider": provider,
                "agent_managed_endpoint": None,
                "agent_managed_api_key": None,
                "agent_model_name": "x",
                "agent_model_timeout_seconds": 1.0,
                "database_url": "postgresql://unused",
            },
        )()
    monkeypatch.setattr(v3_flow, "ManagedEvalModelAdapter", lambda **kw: object())
    monkeypatch.setattr(v3_flow, "_build_executor", lambda *args, **kw: (None, None))

    from umbral.application.agent_evals.v3.releases import (
        load_releases as load_v3_releases,
    )

    releases = load_v3_releases(CONTRACTS / "v3" / "graph-releases-v2.json")
    with_candidate = EvalReleases(
        "2",
        "graph-releases-v2",
        releases.releases + (replace(releases.releases[0], id="graph-release-004"),),
    )
    monkeypatch.setattr(v3_flow, "load_v3_releases", lambda _path: with_candidate)

    def fake_run_suite(**kwargs):
        return _suite(kwargs["release"].id, mode=mode)

    monkeypatch.setattr(v3_flow, "run_suite", fake_run_suite)
    return v3_flow.run_v3_eval(
        settings=settings,
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        cost_cap_usd=5.0,
        contracts_dir=CONTRACTS,
        evidence_dir=tmp_path,
    )


def test_complete_advisory_run_exits_zero_and_writes_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code = _run_flow(monkeypatch, tmp_path, mode="ok")

    assert code == v3_flow.EXIT_OK
    dirs = [entry for entry in tmp_path.iterdir() if entry.is_dir()]
    assert len(dirs) == 1
    assert (dirs[0] / "report.json").exists()
    assert (dirs[0] / "report.md").exists()


def test_safety_blocked_run_exits_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code = _run_flow(monkeypatch, tmp_path, mode="safety")

    assert code == v3_flow.EXIT_BLOCKED
    dirs = [entry for entry in tmp_path.iterdir() if entry.is_dir()]
    assert len(dirs) == 1
    assert (dirs[0] / "report.json").exists()


def test_provider_incomplete_run_exits_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code = _run_flow(monkeypatch, tmp_path, mode="incomplete")

    assert code == v3_flow.EXIT_INCOMPLETE
    dirs = [entry for entry in tmp_path.iterdir() if entry.is_dir()]
    assert len(dirs) == 1
    assert (dirs[0] / "report.json").exists()


def test_unmanaged_configuration_exits_four_without_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code = _run_flow(monkeypatch, tmp_path, mode="ok", provider="fake")

    assert code == v3_flow.EXIT_CONFIG
    assert list(tmp_path.iterdir()) == []


def test_unknown_release_ids_exit_four_without_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code = _run_flow(
        monkeypatch, tmp_path, mode="ok", baseline_id="missing-release"
    )

    assert code == v3_flow.EXIT_CONFIG
    assert list(tmp_path.iterdir()) == []