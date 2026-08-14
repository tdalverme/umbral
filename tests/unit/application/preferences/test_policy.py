"""Policy behavior for durable preference bindings."""

from __future__ import annotations

from uuid import uuid4

import pytest

from umbral.application.preferences.contracts import BindingDraft, PreferencePolicySpec
from umbral.application.preferences.policy import can_supersede, validate_binding


def test_lower_authority_cannot_supersede_higher_authority() -> None:
    assert can_supersede("explicit", "passive") is False
    assert can_supersede("passive", "deliberate_feedback") is True


def test_semantic_binding_requires_a_versioned_embedding() -> None:
    draft = BindingDraft(
        kind="semantic",
        concept_key=None,
        matcher_type="semantic_feature",
        mode="soft",
        params={"weight": 0.1},
        query_embedding=(0.1, 0.2),
        embedding_version_id=None,
        confidence=0.7,
    )

    assert validate_binding(draft, PreferencePolicySpec.v1()) == (
        "preferences.semantic_embedding_version_required",
    )


def test_semantic_binding_cannot_exceed_policy_weight_or_be_hard() -> None:
    draft = BindingDraft.semantic(
        query_embedding=(0.1, 0.2),
        embedding_version_id=uuid4(),
        confidence=0.7,
        weight=0.11,
    )

    assert validate_binding(draft, PreferencePolicySpec.v1()) == (
        "preferences.semantic_weight_exceeds_policy",
    )


def test_policy_rejects_an_adversarial_semantic_cap() -> None:
    with pytest.raises(ValueError, match="semantic_max_weight"):
        PreferencePolicySpec(
            authority_order=("explicit", "deliberate_feedback", "passive"),
            semantic_mode="soft",
            semantic_max_weight=1.0,
            missing_evidence_contribution=0.0,
        )


@pytest.mark.parametrize(
    ("semantic_mode", "missing_evidence_contribution"),
    [("hard", 0.0), ("soft", 0.01)],
)
def test_policy_rejects_nonzero_or_nonsoft_semantic_defaults(
    semantic_mode: str, missing_evidence_contribution: float
) -> None:
    with pytest.raises(ValueError):
        PreferencePolicySpec(
            authority_order=("explicit", "deliberate_feedback", "passive"),
            semantic_mode=semantic_mode,  # type: ignore[arg-type]
            semantic_max_weight=0.10,
            missing_evidence_contribution=missing_evidence_contribution,
        )


def test_unresolved_and_forbidden_factories_cannot_express_computable_state() -> None:
    unresolved = BindingDraft.unresolved("no_reliable_evidence")
    forbidden = BindingDraft.forbidden("fairness_prohibited")

    assert unresolved.concept_key is None
    assert unresolved.matcher_type is None
    assert unresolved.query_embedding is None
    assert unresolved.confidence == 0.0
    assert forbidden.params == {"reason": "fairness_prohibited"}
    assert forbidden.mode == "soft"
