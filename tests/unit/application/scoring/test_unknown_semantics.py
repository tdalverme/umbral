"""Unit tests for unknown vs negative evidence semantics (US3)."""

from __future__ import annotations

from uuid import uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)


def test_unknown_lowers_run_confidence_without_counting_as_mismatch() -> None:
    context = ScoringTestContext()
    profile = build_profile()
    with_unknown = build_listing(total_cost=700.0)
    without_unknown = build_listing(total_cost=650.0)
    context.profiles.rows[profile.profile_id] = profile
    context.observations.observations = {
        with_unknown.listing_id: {
            "balcon": build_observation(
                listing_id=with_unknown.listing_id, concept_key="balcon", value="si"
            )
        },
        without_unknown.listing_id: {
            "balcon": build_observation(
                listing_id=without_unknown.listing_id, concept_key="balcon", value="si"
            ),
            "luminosidad": build_observation(
                listing_id=without_unknown.listing_id,
                concept_key="luminosidad",
                value="alta",
                score=0.9,
                confidence=0.8,
            ),
        },
    }
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(
            build_criterion("balcon", matcher_type="categorical"),
            build_criterion("luminosidad", matcher_type="semantic_feature"),
        ),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(with_unknown, without_unknown),
        run_id=uuid4(),
        correlation_id=uuid4(),
    )
    by_listing = {candidate.listing_id: candidate for candidate in scored}
    first = by_listing[with_unknown.listing_id]
    second = by_listing[without_unknown.listing_id]
    luminosidad = next(
        item for item in first.evaluations if item.criterion_key == "luminosidad"
    )
    assert luminosidad.state == "unknown"
    assert first.confidence < second.confidence
    assert 0 == sum(
        1
        for item in first.evaluations
        if item.state == "mismatch" and item.reason_code == "no_observation_data"
    )


def test_negative_evidence_is_never_confused_with_unknown() -> None:
    context = ScoringTestContext()
    profile = build_profile()
    listing = build_listing()
    context.profiles.rows[profile.profile_id] = profile
    context.observations.observations = {
        listing.listing_id: {
            "balcon": build_observation(
                listing_id=listing.listing_id, concept_key="balcon", value="no"
            )
        }
    }
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(build_criterion("balcon", matcher_type="categorical"),),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        run_id=uuid4(),
        correlation_id=uuid4(),
    )
    balcon = next(
        item for item in scored[0].evaluations if item.criterion_key == "balcon"
    )
    assert balcon.state == "mismatch"
    assert balcon.reason_code == "concept_missing"
    assert balcon.confidence == 1.0
