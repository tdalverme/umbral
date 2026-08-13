"""Unit tests for evaluator assembly through the scoring service (US2)."""

from __future__ import annotations

from uuid import uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)

from umbral.application.scoring.engine import ScoredCandidate


def _service_with_observations(
    *, observation: str | None, concept: str = "balcon"
) -> tuple[ScoringTestContext, tuple[ScoredCandidate, ...]]:
    context = ScoringTestContext()
    profile = build_profile()
    listing = build_listing()
    context.profiles.rows[profile.profile_id] = profile
    context.observations.observations = {
        listing.listing_id: {
            concept: build_observation(
                listing_id=listing.listing_id, concept_key=concept, value=observation
            )
        }
    }
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(build_criterion(concept, matcher_type="categorical"),),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        run_id=uuid4(),
        correlation_id=uuid4(),
    )
    return context, scored


def test_allowed_value_produces_match_evaluation() -> None:
    _, scored = _service_with_observations(observation="si")
    assert len(scored) == 1
    candidate = scored[0]
    assert candidate.score > 0.0
    evaluations = candidate.evaluations
    assert len(evaluations) == 7  # the seed policy criteria
    balcon = next(item for item in evaluations if item.criterion_key == "balcon")
    assert balcon.state == "match"
    assert balcon.score == 1.0
    assert balcon.reason_code == "concept_observed"
    assert balcon.input_refs[0]["kind"] == "observation"


def test_missing_observation_produces_unknown() -> None:
    context = ScoringTestContext()
    profile = build_profile()
    listing = build_listing()
    context.profiles.rows[profile.profile_id] = profile
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(build_criterion("luminosidad", matcher_type="semantic_feature"),),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        run_id=uuid4(),
        correlation_id=uuid4(),
    )
    luminosidad = next(
        item for item in scored[0].evaluations if item.criterion_key == "luminosidad"
    )
    assert luminosidad.state == "unknown"
    assert luminosidad.confidence == 0.0
    assert luminosidad.reason_code == "no_observation_data"


def test_fixed_criteria_are_evaluated_from_profile_and_listing() -> None:
    _, scored = _service_with_observations(observation="si")
    presupuesto = next(
        item for item in scored[0].evaluations if item.criterion_key == "presupuesto"
    )
    assert presupuesto.state == "match"
    assert presupuesto.evidence_refs[0]["kind"] == "listing_field"
    assert presupuesto.evidence_refs[0]["ref"] == "total_cost"
