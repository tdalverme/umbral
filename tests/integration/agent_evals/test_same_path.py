"""Integration test: scripted and managed V5 evals share the production graph."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from umbral.agent.intent import InterpretationContractFailed
from umbral.application.agent_evals.v4.loader import (
    load_dataset,
    load_policy,
    load_releases,
)
from umbral.infrastructure.agent_evals import v4_flow as flow
from umbral.infrastructure.agent_evals.v4_flow import (
    ManagedEvalModelAdapterV4,
    ScriptedEvalModelAdapterV4,
    V5EvalTrialExecutor,
    _EvalServices,
    _settings_from_environment,
    compare_releases,
    run_v4_suite,
)
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed

ROOT = Path(__file__).resolve().parents[3]
V4_DIR = ROOT / "contracts" / "agent-evals" / "v4"


def test_managed_eval_settings_are_loaded_from_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_from_environment(
        _cls: type[Settings], values: dict[str, str]
    ) -> object:
        captured.update(values)
        return object()

    monkeypatch.setenv("UMBRAL_ENV", "local")
    monkeypatch.setenv("AGENT_MODEL_PROVIDER", "managed")
    monkeypatch.setenv("AGENT_MANAGED_ENDPOINT", "http://127.0.0.1:8011")
    monkeypatch.setenv("EVAL_SECRET_NOT_ALLOWED", "must-not-forward")
    monkeypatch.setattr(
        Settings, "from_environment", classmethod(fake_from_environment)
    )

    _settings_from_environment()

    assert captured["UMBRAL_ENV"] == "local"
    assert captured["AGENT_MODEL_PROVIDER"] == "managed"
    assert captured["AGENT_MANAGED_ENDPOINT"] == "http://127.0.0.1:8011"
    assert "EVAL_SECRET_NOT_ALLOWED" not in captured


def test_stale_eval_turn_records_model_contract_failure_instead_of_aborting() -> None:
    services = _EvalServices()

    class FailingTurnService:
        def load_context(self, **_: object) -> object:
            return object()

        def interpret(self, **_: object) -> object:
            raise InterpretationContractFailed("evidence span does not match message")

        def _failed_result(self, _context: object, stage: str) -> str:
            return stage

    services.turn_service = FailingTurnService()

    result = services.run_stale_turn(SimpleNamespace(user="untrusted model text"))

    assert result == "interpretation_failure"


def test_scripted_and_managed_v5_use_the_same_graph_builder() -> None:
    assert ScriptedEvalModelAdapterV4.fidelity == "scripted"
    executor = V5EvalTrialExecutor(contracts_dir=ROOT / "contracts")
    from umbral.agent.graph import build_graph

    assert executor.graph_factory is build_graph


def test_eval_executor_passes_the_published_catalog_to_v5_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    case = next(item for item in dataset.cases if item.id == "v4.desire_preservation")
    release = next(
        item for item in releases.releases if item.id == "graph-release-005"
    )
    received: dict[str, object] = {}
    compiler = flow.InterpretationCompiler

    def record_catalog(**kwargs: object) -> object:
        received["catalog"] = kwargs["concept_catalog"]
        return compiler(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(flow, "InterpretationCompiler", record_catalog)

    V5EvalTrialExecutor(contracts_dir=ROOT / "contracts").execute(
        case=case,
        release=release,
        adapter=ScriptedEvalModelAdapterV4(),
        trial_index=0,
        attempt_index=0,
    )

    catalog = received["catalog"]
    assert isinstance(catalog, tuple)
    published = load_concepts_seed().concepts
    assert {item["key"] for item in catalog} == {concept.key for concept in published}
    assert {item["key"] for item in catalog} >= {
        "balcon",
        "luminosidad",
        "proximidad_cafes",
        "acceso_escuela",
        "acceso_salud",
    }
    assert all(
        {"description", "matcher_type", "computable", "aliases"} <= set(item)
        for item in catalog
    )


def test_managed_adapter_injects_declared_provider_failure() -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    case = next(item for item in dataset.cases if item.id == "v4.provider_failure")
    release = next(
        item for item in releases.releases if item.id == "graph-release-005"
    )
    settings = SimpleNamespace(
        agent_model_provider="managed",
        agent_managed_endpoint="http://127.0.0.1:8011/v1/structured",
        agent_managed_api_key="local-eval",
        agent_model_name="gpt-4.1-mini",
    )

    gateway = ManagedEvalModelAdapterV4(settings=settings).gateway_for(
        case=case, release=release, trial_index=0, attempt_index=0
    )
    result = gateway.generate_structured(
        messages=(),
        schema={},
        schema_version="conversation-interpretation",
        prompt_version="interpretation",
        model_version="gpt-4.1-mini",
    )

    assert result.status == "error"
    assert result.error_code == "provider.timeout"


def test_managed_adapter_injects_declared_reply_failure() -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    case = next(item for item in dataset.cases if item.id == "v4.reply_fallback")
    release = next(
        item for item in releases.releases if item.id == "graph-release-005"
    )
    settings = SimpleNamespace(
        agent_model_provider="managed",
        agent_managed_endpoint="http://127.0.0.1:8011/v1/structured",
        agent_managed_api_key="local-eval",
        agent_model_name="gpt-4.1-mini",
    )

    gateway = ManagedEvalModelAdapterV4(settings=settings).gateway_for(
        case=case, release=release, trial_index=0, attempt_index=0
    )
    result = gateway.generate_structured(
        messages=(),
        schema={},
        schema_version="conversation-reply",
        prompt_version="reply",
        model_version="gpt-4.1-mini",
    )

    assert result.status == "error"
    assert result.error_code == "provider.timeout"


def test_v5_executor_rejects_the_legacy_v4_release() -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    case = dataset.cases[0]
    legacy = next(
        item for item in releases.releases if item.id == "graph-release-003"
    )

    with pytest.raises(ValueError, match="requires_v5_release"):
        V5EvalTrialExecutor(contracts_dir=ROOT / "contracts").execute(
            case=case,
            release=legacy,
            adapter=ScriptedEvalModelAdapterV4(),
            trial_index=0,
            attempt_index=0,
        )


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
