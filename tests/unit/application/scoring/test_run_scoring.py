"""Unit tests for deterministic run scoring (US4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)

from umbral.application.scoring.engine import ScoredCandidate, score_candidates
from umbral.application.scoring.policy import parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import load_scoring_policy_seed


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
        score_policy_version=context.service.pin_policy_version(),
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
        score_policy_version=context.service.pin_policy_version(),
    )
    balcon = next(
        item for item in scored[0].evaluations if item.criterion_key == "balcon"
    )
    assert balcon.criterion_version.startswith("policy:")
    assert balcon.input_refs[0]["ref"] == str(observation.observation_id)
    assert balcon.input_refs[0]["version"] == str(observation.extraction_version_id)
    assert balcon.contribution > 0.0


def test_scoring_does_not_change_when_unasked_default_signal_changes() -> None:
    profile = build_profile()
    listing = build_listing()
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(),
    )
    policy = parse_policy_document(load_scoring_policy_seed(), load_matcher_types())
    common = dict(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=datetime.now(timezone.utc),
    )
    without_defaults = score_candidates(observations={}, **common)
    with_defaults = score_candidates(
        observations={
            listing.listing_id: {
                "balcon": build_observation(
                    listing_id=listing.listing_id, concept_key="balcon", value="si"
                ),
                "estado_general": build_observation(
                    listing_id=listing.listing_id,
                    concept_key="estado_general",
                    value="bueno",
                ),
            }
        },
        **common,
    )

    assert [item.score for item in without_defaults] == [
        item.score for item in with_defaults
    ]
    assert all(
        item.criterion_key not in {"balcon", "estado_general"}
        for item in without_defaults[0].evaluations
    )
