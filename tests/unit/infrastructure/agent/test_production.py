"""Unit tests for the single production conversation stack."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from umbral.infrastructure.agent import production
from umbral.infrastructure.agent.production import build_production_stack
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


def _settings() -> Settings:
    return Settings.from_environment(dict(_LOCAL_BASE))


def test_single_stack_wires_pending_proposals_to_graph_runs(
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

    def build_conversation_graph(**_kwargs: object) -> object:
        return object()

    def build_turn_service(**_kwargs: object) -> object:
        return object()

    def session_factory() -> Session:
        raise AssertionError("session factory should not be called")

    monkeypatch.setattr(production, "SearchProfileUpdateProposals", _Proposals)
    monkeypatch.setattr(production, "SqlAlchemyGraphRunRepository", build_runs)
    monkeypatch.setattr(production, "create_postgres_saver", build_saver)
    monkeypatch.setattr(
        production, "_build_concept_catalog", lambda _factory: ()
    )
    monkeypatch.setattr(
        production, "_build_preference_service", lambda _factory: None
    )
    from umbral.infrastructure.conversation import (
        composition as conversation_composition,
    )

    monkeypatch.setattr(
        conversation_composition, "build_conversation_graph", build_conversation_graph
    )
    monkeypatch.setattr(
        conversation_composition,
        "build_conversation_turn_service",
        build_turn_service,
    )
    criteria = object()

    production.build_production_stack(
        settings=_settings(),
        session_factory=session_factory,
        database_url="postgresql://u:p@127.0.0.1/db",
        radar=object(),
        scoring=object(),
        feedback=object(),
        criteria=criteria,
    )

    assert captured["waiting_runs"] is graph_runs
    assert captured["criteria"] is criteria


def test_release_selector_settings_are_no_longer_accepted() -> None:
    values = dict(_LOCAL_BASE)
    values["AGENT_GRAPH_RELEASE_ID"] = "graph-release-005"
    with pytest.raises(ValueError, match="CONFIG_UNKNOWN_SETTING"):
        Settings.from_environment(values)


def test_catalog_loader_rejects_an_empty_active_registry(
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
        production._build_concept_catalog(lambda: None)  # type: ignore[arg-type]


def test_only_one_production_builder_exists() -> None:
    assert callable(build_production_stack)
    assert not hasattr(production, "build_production_agent_stack")
    assert not hasattr(production, "build_production_copilot_stack")
    assert not hasattr(production, "select_production_conversation_builder")
    assert SimpleNamespace is not None
