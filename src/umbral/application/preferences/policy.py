"""Deterministic policy for authority and binding validity."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.preferences.contracts import (
    ABSOLUTE_SEMANTIC_MAX_WEIGHT,
    BindingDraft,
    PreferenceAuthority,
    PreferencePolicySpec,
)

_AUTHORITY_ORDER: Mapping[PreferenceAuthority, int] = {
    "passive": 0,
    "deliberate_feedback": 1,
    "explicit": 2,
}


def can_supersede(current: PreferenceAuthority, incoming: PreferenceAuthority) -> bool:
    """Return whether incoming authority may replace the current expression."""

    return _AUTHORITY_ORDER[incoming] >= _AUTHORITY_ORDER[current]


def validate_binding(
    draft: BindingDraft, policy: PreferencePolicySpec
) -> tuple[str, ...]:
    """Return stable error codes for an interpretation that cannot be persisted."""

    errors: list[str] = []
    if not 0.0 <= draft.confidence <= 1.0:
        errors.append("preferences.binding_confidence_out_of_range")

    if draft.kind == "structured":
        if not draft.concept_key:
            errors.append("preferences.structured_concept_required")
        if draft.matcher_type is None:
            errors.append("preferences.structured_matcher_required")
        if draft.query_embedding is not None or draft.embedding_version_id is not None:
            errors.append("preferences.structured_embedding_forbidden")
    elif draft.kind == "semantic":
        if draft.concept_key is not None:
            errors.append("preferences.semantic_concept_forbidden")
        if draft.matcher_type != "semantic_feature":
            errors.append("preferences.semantic_matcher_invalid")
        if draft.mode != policy.semantic_mode:
            errors.append("preferences.semantic_must_be_soft")
        if not draft.query_embedding:
            errors.append("preferences.semantic_embedding_required")
        if draft.embedding_version_id is None:
            errors.append("preferences.semantic_embedding_version_required")
        weight = draft.params.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            errors.append("preferences.semantic_weight_required")
        elif not 0.0 <= float(weight) <= min(
            policy.semantic_max_weight, ABSOLUTE_SEMANTIC_MAX_WEIGHT
        ):
            errors.append("preferences.semantic_weight_exceeds_policy")
    else:
        if draft.concept_key is not None or draft.matcher_type is not None:
            errors.append("preferences.noncomputable_binding_must_be_unbound")
        if draft.mode != "soft":
            errors.append("preferences.noncomputable_binding_must_be_soft")
        if draft.query_embedding is not None or draft.embedding_version_id is not None:
            errors.append("preferences.noncomputable_embedding_forbidden")
        if draft.confidence != 0.0:
            errors.append("preferences.noncomputable_confidence_must_be_zero")
    if (
        draft.kind == "structured"
        and draft.mode == "hard"
        and draft.confirmation is None
    ):
        errors.append("preferences.hard_binding_requires_confirmation")
    if draft.kind != "structured" and draft.confirmation is not None:
        errors.append("preferences.nonstructured_confirmation_forbidden")
    return tuple(errors)
