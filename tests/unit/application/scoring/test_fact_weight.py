# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Fact weight reaches the ranking (fase 3, US3)."""

from __future__ import annotations

from uuid import uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)


def _scored_with_fact(fact_weight: float | None) -> float:
    context = ScoringTestContext()
    profile = build_profile()
    listing = build_listing()
    context.profiles.rows[profile.profile_id] = profile
    context.observations.observations = {
        listing.listing_id: {
            "moderno": build_observation(
                listing_id=listing.listing_id,
                concept_key="moderno",
                value="moderno",
                score=1.0,
                confidence=0.9,
            )
        }
    }
    compiled = build_criterion(
        "moderno",
        matcher_type="semantic_feature",
        params={"concept": "moderno", "polarity": "positive"},
        weight=fact_weight,
    )
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(compiled,),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        run_id=uuid4(),
        correlation_id=uuid4(),
        score_policy_version=context.service.pin_policy_version(),
    )
    return scored[0].score


def test_fact_weight_from_out_of_policy_concept_drives_the_ranking() -> None:
    heavy = _scored_with_fact(0.5)
    light = _scored_with_fact(0.05)
    assert heavy > light
    # A fact with weight must add a real contribution above the base criteria.
    assert heavy > 0.5


def test_fact_without_weight_falls_back_to_policy() -> None:
    context = ScoringTestContext()
    profile = build_profile()
    listing = build_listing()
    context.profiles.rows[profile.profile_id] = profile
    context.observations.observations = {
        listing.listing_id: {
            "balcon": build_observation(
                listing_id=listing.listing_id, concept_key="balcon", value="true"
            )
        }
    }
    compiled = build_criterion(
        "balcon",
        matcher_type="categorical",
        params={"allowed_values": ["true", "false"], "polarity": "positive"},
        weight=None,
    )
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(compiled,),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        run_id=uuid4(),
        correlation_id=uuid4(),
        score_policy_version=context.service.pin_policy_version(),
    )
    balcon = next(
        item
        for item in scored[0].evaluations
        if item.criterion_key == "balcon"
    )
    assert balcon.state == "match"
