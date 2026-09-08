"""Tests for criteria explicitly activated by a radar profile."""

from __future__ import annotations

from uuid import uuid4

from tests.support.radar import build_profile
from tests.support.scoring import build_compilation, build_criterion

from umbral.application.scoring.active_criteria import active_criterion_keys
from umbral.application.scoring.policy import parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import load_scoring_policy_seed


def _policy():
    return parse_policy_document(load_scoring_policy_seed(), load_matcher_types())


def test_policy_criteria_not_declared_by_profile_are_inactive() -> None:
    profile = build_profile()
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(),
    )

    active = active_criterion_keys(profile, compilation, _policy())

    assert "balcon" not in active
    assert "estado_general" not in active


def test_compiled_soft_criterion_is_active() -> None:
    profile = build_profile()
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(build_criterion("luminosidad", matcher_type="semantic_feature"),),
    )

    active = active_criterion_keys(profile, compilation, _policy())

    assert "luminosidad" in active
