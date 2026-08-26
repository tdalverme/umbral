"""Unit tests for the V5 runtime release selector."""

from __future__ import annotations

import pytest

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