"""Parser unit tests for the graph releases registry (T007)."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from umbral.application.agent_evals.contracts import (
    AgentEvalsValidationError,
    ReleaseActivation,
)
from umbral.application.agent_evals.releases import activation_allowed, parse_releases


def _releases() -> dict[str, object]:
    return {
        "contract_version": "1",
        "registry_version": "graph-releases-v1",
        "releases": [
            {
                "id": "graph-release-001",
                "components": {
                    "prompt_versions": ["agent-intent-v1", "agent-reply-v2"],
                    "model_version": "provider-x-model-y",
                    "state_schema_version": "chat-state-v3",
                    "topology_version": "chat-topology-v3",
                    "intent_schema_version": "intent-schema-v3",
                    "price_table_version": "price-table-v1",
                    "touches_prompts_or_model": False,
                },
                "owner": "team-agent",
                "justification": "release inicial",
                "affected_case_ids": ["conversation-001"],
                "activation": {
                    "status": "active",
                    "approved_by": None,
                    "approval_evidence": None,
                    "reverted_reason": None,
                },
                "date": "2026-08-10",
            }
        ],
    }


def test_releases_parse_with_active_release() -> None:
    registry = parse_releases(_releases(), known_case_ids={"conversation-001"})
    release = registry.active_release()
    assert release is not None and release.id == "graph-release-001"
    assert activation_allowed(release) is True


def test_activation_is_automatic_when_deterministic_components() -> None:
    registry = parse_releases(_releases())
    assert activation_allowed(registry.releases[0]) is True


def test_activation_requires_approval_when_prompts_or_model_change() -> None:
    data = _releases()
    release = dict(data["releases"][0])
    components = dict(release["components"])
    components["touches_prompts_or_model"] = True
    release["components"] = components
    data["releases"] = [release]
    registry = parse_releases(data)
    release = registry.releases[0]
    assert activation_allowed(release) is False
    approved = asdict(release.activation)
    approved["approved_by"] = "operator-a"
    approved["approval_evidence"] = "eval-report-graph-release-002"
    approved_release = replace(release, activation=ReleaseActivation(**approved))
    assert activation_allowed(approved_release) is True


def test_releases_reject_unknown_affected_case() -> None:
    data = _releases()
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_releases(data, known_case_ids={"conversation-999"})
    assert any(
        "agent_evals.unknown_affected_case" in code
        for code in excinfo.value.error_codes
    )


def test_releases_reject_duplicate_ids() -> None:
    data = _releases()
    data["releases"] = [data["releases"][0], data["releases"][0]]
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_releases(data)
    assert any(
        "agent_evals.duplicate_release" in code for code in excinfo.value.error_codes
    )


def test_releases_reject_unknown_activation_status() -> None:
    data = _releases()
    release = dict(data["releases"][0])
    activation = dict(release["activation"])
    activation["status"] = "half-open"
    release["activation"] = activation
    data["releases"] = [release]
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_releases(data)
    assert any(
        "agent_evals.unknown_activation_status" in code
        for code in excinfo.value.error_codes
    )
