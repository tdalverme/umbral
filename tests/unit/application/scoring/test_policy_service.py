"""Unit tests for the scoring policy lifecycle (US1)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.support.scoring import SEED, ScoringTestContext

from umbral.application.scoring.contracts import ScoringValidationError


def test_seed_registry_registers_once_and_is_idempotent() -> None:
    context = ScoringTestContext()
    assert context.service.seed_registry(uuid4()) == 1
    assert context.service.seed_registry(uuid4()) == 0
    assert context.service.latest_policy_document().score_policy_version == (
        "scoring-policy-v1"
    )


def test_register_policy_version_is_append_only() -> None:
    context = ScoringTestContext()
    first = context.service.register_policy_version(
        policy_key="scoring-policy-v1", payload=SEED, correlation_id=uuid4()
    )
    second = context.service.register_policy_version(
        policy_key="scoring-policy-v1", payload=SEED, correlation_id=uuid4()
    )
    assert first.policy_version == 1
    assert second.policy_version == 2
    assert first.version_id != second.version_id
    assert context.service.latest_policy_document().score_policy_version == (
        "scoring-policy-v1"
    )


def test_invalid_policy_document_is_rejected_without_persisting() -> None:
    context = ScoringTestContext()
    invalid = dict(SEED)
    invalid["criteria"] = [
        {**dict(SEED["criteria"][0]), "weight": 0.5},
        dict(SEED["criteria"][1]),
        dict(SEED["criteria"][2]),
        dict(SEED["criteria"][3]),
        dict(SEED["criteria"][4]),
        dict(SEED["criteria"][5]),
        dict(SEED["criteria"][6]),
    ]
    with pytest.raises(ScoringValidationError):
        context.service.register_policy_version(
            policy_key="scoring-policy-v1", payload=invalid, correlation_id=uuid4()
        )
    assert context.policies.latest_version("scoring-policy-v1") is None
