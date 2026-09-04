"""Unit tests for the V5 runtime release selector."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from umbral.infrastructure.agent import production
from umbral.infrastructure.agent.production import (
    _require_v5_activation,
    build_production_copilot_stack,
    build_production_v5_stack,
    select_production_conversation_builder,
)
from umbral.infrastructure.config.settings import Settings

_LOCAL_BASE = {
    "UMBRAL_ENV": "local",
    "UMBRAL_RELEASE_ID": "test",
    "UMBRAL_RELEASE_MANIFEST": "<local>",
    "DATABASE_URL": "postgresql://u:p@127.0.0.1/db",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "OBJECT_STORE_BACKEND": "filesystem",
    "OBJECT_STORE_ROOT": ".umbral-local",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
    "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
}


def _settings(release_id: str, evidence: str = "") -> Settings:
    values = dict(_LOCAL_BASE)
    values["AGENT_GRAPH_RELEASE_ID"] = release_id
    if evidence:
        values["AGENT_V5_ACTIVATION_EVIDENCE"] = evidence
    return Settings.from_environment(values)


def test_v4_release_selects_the_copilot_builder() -> None:
    builder = select_production_conversation_builder(
        _settings("graph-release-003")
    )

    assert builder is build_production_copilot_stack


def test_v5_release_selects_the_v5_builder_with_activation_evidence() -> None:
    builder = select_production_conversation_builder(
        _settings(
            "graph-release-005", evidence="agent-evals-v4-evidence-005"
        )
    )

    assert builder is build_production_v5_stack


def test_v5_without_activation_evidence_fails_closed() -> None:
    with pytest.raises(ValueError) as exc:
        select_production_conversation_builder(_settings("graph-release-005"))

    assert "activation_evidence_required" in str(exc.value)


def test_unknown_release_fails_closed() -> None:
    with pytest.raises(ValueError) as exc:
        select_production_conversation_builder(_settings("graph-release-999"))

    assert "unknown_release" in str(exc.value)


def test_activation_requirement_accepts_registered_evidence() -> None:
    settings = _settings(
        "graph-release-005", evidence="agent-evals-v4-evidence-005"
    )

    _require_v5_activation(settings)  # does not raise


def test_default_release_keeps_the_v4_path() -> None:
    builder = select_production_conversation_builder(_settings("graph-release-001"))

    assert builder is build_production_copilot_stack


def test_v3_stack_wires_pending_proposals_to_graph_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    graph_runs = object()

    class _Proposals:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    def build_runs(_session_factory: object) -> object:
        return graph_runs

    def build_saver(*_args: object, **_kwargs: object) -> object:
        return object()

    def build_graph(**_kwargs: object) -> object:
        return SimpleNamespace(deps=SimpleNamespace(sinks=SimpleNamespace()))

    def session_factory() -> Session:
        raise AssertionError("session factory should not be called")

    monkeypatch.setattr(production, "SearchProfileUpdateProposals", _Proposals)
    monkeypatch.setattr(production, "SqlAlchemyGraphRunRepository", build_runs)
    monkeypatch.setattr(production, "create_postgres_saver", build_saver)
    monkeypatch.setattr(production, "build_topology_v3", build_graph)

    production.build_production_agent_stack(
        settings=_settings("graph-release-001"),
        session_factory=session_factory,
        database_url="postgresql://u:p@127.0.0.1/db",
        radar=object(),
        scoring=object(),
        feedback=object(),
        criteria=object(),
    )

    assert captured["waiting_runs"] is graph_runs


def test_v5_catalog_loader_rejects_an_empty_active_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from umbral.infrastructure.db.repositories import criteria

    class _EmptyConceptRepository:
        def __init__(self, _session_factory: object) -> None:
            pass

        def list_active(self) -> tuple[object, ...]:
            return ()

    monkeypatch.setattr(
        criteria, "SqlAlchemyConceptRepository", _EmptyConceptRepository
    )

    with pytest.raises(ValueError, match="active concept registry is empty"):
        production._build_v5_concept_catalog(lambda: None)  # type: ignore[arg-type]
