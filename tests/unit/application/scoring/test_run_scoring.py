"""Unit tests for deterministic run scoring (US4)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)

from umbral.application.scoring.engine import ScoredCandidate


def _scored_twice() -> tuple[tuple[ScoredCandidate, ...], tuple[ScoredCandidate, ...]]:
    context = ScoringTestContext()
    profile = build_profile()
    listings = (build_listing(total_cost=700.0), build_listing(total_cost=500.0))
    context.profiles.rows[profile.profile_id] = profile
    context.observations.observations = {
        listing.listing_id: {
            "balcon": build_observation(
                listing_id=listing.listing_id, concept_key="balcon", value="si"
            )
        }
        for listing in listings
    }
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(build_criterion("balcon", matcher_type="categorical"),),
    )
    kwargs: dict[str, Any] = dict(
        profile=profile,
        compilation=compilation,
        candidates=listings,
        run_id=uuid4(),
        correlation_id=uuid4(),
    )
    first = context.service.score_run(**kwargs)
    second = context.service.score_run(**kwargs)
    return first, second


def test_identical_inputs_produce_identical_order_and_breakdown() -> None:
    first, second = _scored_twice()
    assert [candidate.listing_id for candidate in first] == [
        candidate.listing_id for candidate in second
    ]
    assert [candidate.score for candidate in first] == [
        candidate.score for candidate in second
    ]

    def breakdown(
        candidates: tuple[ScoredCandidate, ...],
    ) -> list[list[tuple[str, float, float, str]]]:
        return [
            [
                (
                    item.criterion_key,
                    item.score,
                    item.contribution,
                    item.reason_code,
                )
                for item in candidate.evaluations
            ]
            for candidate in candidates
        ]

    assert breakdown(first) == breakdown(second)


def test_evaluations_carry_versioned_input_refs_and_reason() -> None:
    context = ScoringTestContext()
    profile = build_profile()
    listing = build_listing()
    context.profiles.rows[profile.profile_id] = profile
    observation = build_observation(
        listing_id=listing.listing_id, concept_key="balcon", value="si"
    )
    context.observations.observations = {listing.listing_id: {"balcon": observation}}
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
    assert balcon.criterion_version.startswith("policy:")
    assert balcon.input_refs[0]["ref"] == str(observation.observation_id)
    assert balcon.input_refs[0]["version"] == str(observation.extraction_version_id)
    assert balcon.contribution > 0.0
