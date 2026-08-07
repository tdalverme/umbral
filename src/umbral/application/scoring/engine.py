"""Pure, deterministic scoring v1 engine.

The same inputs (profile snapshot, compilation, candidates, observations and
policy) always produce the same order, scores and breakdown. The engine never
performs I/O: the run job loads the frozen inputs first (FR-008, SC-001).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from umbral.application.criteria.contracts import Compilation, ListingObservation
from umbral.application.radar.contracts import SearchProfile
from umbral.application.scoring.contracts import CriterionEvaluation
from umbral.application.scoring.evaluators import (
    EvaluationResult,
    evaluate_fixed_criterion,
    evaluate_observation_criterion,
)
from umbral.application.scoring.policy import (
    PolicyCriterion,
    ScoringPolicyDoc,
    is_fixed_criterion,
)
from umbral.application.silver.contracts import NormalizedListing

ObservationsByConcept = Mapping[str, ListingObservation]
ObservationsByListing = Mapping[UUID, ObservationsByConcept]


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """One candidate with its frozen evaluation set."""

    listing_id: UUID
    score: float
    confidence: float
    contributions: Mapping[str, object]
    evaluations: tuple[CriterionEvaluation, ...]


class PolicyRunEngine(Protocol):
    """Scoring v1 hook consumed by the radar run pipeline."""

    def compilation_for(self, profile_version_id: UUID) -> Compilation | None: ...

    def score_run(
        self,
        *,
        profile: SearchProfile,
        compilation: Compilation,
        candidates: tuple[NormalizedListing, ...],
        run_id: UUID,
        correlation_id: UUID,
    ) -> tuple[ScoredCandidate, ...]: ...


def score_candidates(
    *,
    profile: SearchProfile,
    compilation: Compilation,
    candidates: tuple[NormalizedListing, ...],
    observations: ObservationsByListing,
    policy: ScoringPolicyDoc,
    run_id: UUID,
    correlation_id: UUID,
    now: datetime,
) -> tuple[ScoredCandidate, ...]:
    """Score every candidate against the policy; returns frozen candidates."""

    scored: list[ScoredCandidate] = []
    for listing in candidates:
        candidate = _score_candidate(
            profile=profile,
            compilation=compilation,
            listing=listing,
            observations=observations.get(listing.listing_id, {}),
            policy=policy,
            run_id=run_id,
            correlation_id=correlation_id,
            now=now,
        )
        if candidate is not None:
            scored.append(candidate)
    if policy.tie_break == ("score", "total_cost_asc", "listing_id_asc"):
        scored.sort(
            key=lambda item: (
                -item.score,
                _total_cost(item.listing_id, candidates),
                str(item.listing_id),
            )
        )
    else:
        scored.sort(key=lambda item: (-item.score, str(item.listing_id)))
    return tuple(scored)


def _score_candidate(
    *,
    profile: SearchProfile,
    compilation: Compilation,
    listing: NormalizedListing,
    observations: ObservationsByConcept,
    policy: ScoringPolicyDoc,
    run_id: UUID,
    correlation_id: UUID,
    now: datetime,
) -> ScoredCandidate | None:
    version_key = f"policy:{policy.score_policy_version}"
    evaluations: list[CriterionEvaluation] = []
    contribution_sum = 0.0
    excluded = False
    for criterion in policy.criteria:
        result, input_refs = _evaluate_criterion(
            criterion, profile, listing, observations
        )
        if criterion.gate == "exclude_on_mismatch" and result.state == "mismatch":
            excluded = True
            break
        contribution = round(criterion.weight * result.score, 6)
        contribution_sum += contribution
        evaluations.append(
            _evaluation(
                criterion=criterion,
                run_id=run_id,
                listing_id=listing.listing_id,
                version_key=version_key,
                result=result,
                input_refs=input_refs,
                contribution=contribution,
                now=now,
                correlation_id=correlation_id,
            )
        )
    if excluded:
        return None
    frozen_evaluations = tuple(evaluations)
    total = _apply_deltas(contribution_sum, policy, frozen_evaluations)
    if any(
        criterion.gate == "cap_0.6_on_mismatch"
        and (gate_result := _result_for(frozen_evaluations, criterion.key)) is not None
        and gate_result.state == "mismatch"
        for criterion in policy.criteria
    ):
        total = min(total, 0.6)
    if any(
        criterion.gate == "cap_0.6_on_unknown"
        and (gate_result := _result_for(frozen_evaluations, criterion.key)) is not None
        and gate_result.state == "unknown"
        for criterion in policy.criteria
    ):
        total = min(total, 0.6)
    score = round(max(0.0, min(1.0, total)), policy.score_round)
    confidence = _run_confidence(frozen_evaluations, policy)
    contributions: dict[str, object] = {
        criterion.key: _contribution_score(frozen_evaluations, criterion.key)
        for criterion in policy.criteria
    }
    contributions["score_policy_version"] = policy.score_policy_version
    return ScoredCandidate(
        listing_id=listing.listing_id,
        score=score,
        confidence=confidence,
        contributions=contributions,
        evaluations=tuple(evaluations),
    )


def _evaluate_criterion(
    criterion: PolicyCriterion,
    profile: SearchProfile,
    listing: NormalizedListing,
    observations: ObservationsByConcept,
) -> tuple[EvaluationResult, tuple[Mapping[str, object], ...]]:
    if is_fixed_criterion(criterion.key):
        result = evaluate_fixed_criterion(
            criterion.key,
            budget_max=profile.budget_max,
            total_cost=listing.total_cost,
            min_rooms=profile.min_rooms,
            rooms=listing.rooms,
            surface_min=profile.surface_min,
            surface_max=profile.surface_max,
            surface_m2=listing.surface_m2,
            zones=profile.zones,
            neighborhood=listing.neighborhood,
            geo_precision=listing.geo_precision,
        )
        field = {
            "presupuesto": "total_cost",
            "ambientes": "rooms",
            "superficie": "surface_m2",
            "ubicacion": "neighborhood",
        }.get(criterion.key, criterion.key)
        refs = ({"kind": "listing_field", "ref": field, "version": "silver-v1"},)
        return result, refs
    observation = observations.get(criterion.concept)
    if observation is None:
        unknown = EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")
        return unknown, ()
    result = evaluate_observation_criterion(
        criterion, observation.value, observation.score, observation.confidence
    )
    refs = (
        {
            "kind": "observation",
            "ref": str(observation.observation_id),
            "version": str(observation.extraction_version_id or ""),
        },
    )
    return result, refs


def _evaluation(
    *,
    criterion: PolicyCriterion,
    run_id: UUID,
    listing_id: UUID,
    version_key: str,
    result: EvaluationResult,
    input_refs: tuple[Mapping[str, object], ...],
    contribution: float,
    now: datetime,
    correlation_id: UUID,
) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=run_id,
        listing_id=listing_id,
        criterion_key=criterion.key,
        criterion_version=version_key,
        matcher_type=criterion.matcher_type,
        params=dict(criterion.params),
        input_refs=input_refs,
        score=result.score,
        confidence=result.confidence,
        state=result.state,
        contribution=contribution,
        reason_code=result.reason_code,
        evidence_refs=input_refs,
        created_at=now,
        correlation_id=correlation_id,
    )


def _apply_deltas(
    base: float,
    policy: ScoringPolicyDoc,
    evaluations: tuple[CriterionEvaluation, ...],
) -> float:
    by_key = {evaluation.criterion_key: evaluation for evaluation in evaluations}
    for adjustment in (*policy.bonuses, *policy.penalties):
        evaluation = by_key.get(adjustment.criterion)
        if evaluation is not None and evaluation.state == adjustment.state:
            base += adjustment.delta
    return base


def _result_for(
    evaluations: tuple[CriterionEvaluation, ...], criterion_key: str
) -> CriterionEvaluation | None:
    return next(
        (item for item in evaluations if item.criterion_key == criterion_key), None
    )


def _contribution_score(
    evaluations: tuple[CriterionEvaluation, ...], criterion_key: str
) -> float:
    entry = _result_for(evaluations, criterion_key)
    return entry.score if entry is not None else 0.0


def _run_confidence(
    evaluations: tuple[CriterionEvaluation, ...],
    policy: ScoringPolicyDoc,
) -> float:
    if not evaluations:
        return 0.0
    base = sum(item.confidence for item in evaluations) / len(evaluations)
    unknown_count = sum(1 for item in evaluations if item.state == "unknown")
    penalty = policy.confidence.get("unknown_penalty", 0.2)
    return round(max(0.0, base - penalty * unknown_count), 3)


def _total_cost(listing_id: UUID, candidates: tuple[NormalizedListing, ...]) -> float:
    for listing in candidates:
        if listing.listing_id == listing_id:
            return listing.total_cost or 0.0
    return 0.0
