"""Integration test: scripted and managed V5 evals share the production graph."""

from __future__ import annotations

from pathlib import Path

from umbral.application.agent_evals.v4.loader import (
    load_dataset,
    load_policy,
    load_releases,
)
from umbral.infrastructure.agent_evals.v4_flow import (
    ScriptedEvalModelAdapterV4,
    V5EvalTrialExecutor,
    compare_releases,
    run_v4_suite,
)

ROOT = Path(__file__).resolve().parents[3]
V4_DIR = ROOT / "contracts" / "agent-evals" / "v4"


def test_scripted_and_managed_v5_use_the_same_graph_builder() -> None:
    assert ScriptedEvalModelAdapterV4.fidelity == "scripted"
    executor = V5EvalTrialExecutor(contracts_dir=ROOT / "contracts")
    from umbral.agent.graph_v5 import build_graph_v5

    assert executor.graph_factory is build_graph_v5


def test_identical_component_releases_are_labeled_replicates() -> None:
    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    by_id = {release.id: release for release in releases.releases}
    comparison = compare_releases(
        baseline=(),
        candidate=(),
        baseline_release=by_id["graph-release-003"],
        candidate_release=by_id["graph-release-003"],
    )
    assert comparison.kind == "statistical_replica"
    assert comparison.functional_delta is None


def test_scripted_suite_runs_the_v5_cases_through_the_production_path() -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    policy = load_policy(V4_DIR / "eval-policy-v4.json")
    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    candidate = next(
        release for release in releases.releases if release.id == "graph-release-005"
    )

    trials = run_v4_suite(
        dataset=dataset,
        release=candidate,
        adapter=ScriptedEvalModelAdapterV4(),
        executor=V5EvalTrialExecutor(contracts_dir=ROOT / "contracts"),
        policy=policy,
    )

    assert len(trials) == len(dataset.cases)
    for trial in trials:
        assert trial.release_id == "graph-release-005"
        assert trial.turns
        assert trial.safety_ok
        assert trial.quality_ok