"""Shared, deterministic activation rules for scoring criteria."""

from __future__ import annotations

from umbral.application.criteria.contracts import Compilation
from umbral.application.radar.contracts import SearchProfile
from umbral.application.scoring.policy import (
    PolicyCriterion,
    ScoringPolicyDoc,
    is_fixed_criterion,
)


def criterion_is_active(
    criterion: PolicyCriterion,
    profile: SearchProfile,
    compiled_concepts: frozenset[str],
) -> bool:
    """Return whether a policy criterion was declared by this radar."""

    if is_fixed_criterion(criterion.key):
        return _fixed_criterion_declared(criterion.key, profile)
    return criterion.concept in compiled_concepts


def active_criterion_keys(
    profile: SearchProfile,
    compilation: Compilation,
    policy: ScoringPolicyDoc,
) -> frozenset[str]:
    """Return policy and dynamic criterion keys active for a radar run."""

    compiled_concepts = frozenset(
        criterion.concept_key for criterion in compilation.criteria
    )
    policy_concepts = {criterion.concept for criterion in policy.criteria}
    active_policy_keys = {
        criterion.key
        for criterion in policy.criteria
        if criterion_is_active(criterion, profile, compiled_concepts)
    }
    dynamic_keys = compiled_concepts - policy_concepts
    return frozenset(active_policy_keys | dynamic_keys)


def _fixed_criterion_declared(key: str, profile: SearchProfile) -> bool:
    if key == "presupuesto":
        return profile.budget_max is not None
    if key == "ambientes":
        return profile.min_rooms is not None
    if key == "superficie":
        return profile.surface_min is not None or profile.surface_max is not None
    if key == "ubicacion":
        return bool(profile.zones)
    return False
