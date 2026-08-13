"""Shared builders for scoring service unit tests with in-memory adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.fakes.scoring import (
    FakeCompilationReader,
    FakeEvaluationRepository,
    FakeItemReader,
    FakeListingReader,
    FakeObservationReader,
    FakePolicyRepository,
    FakeProfileReader,
    FakeRunReader,
    FakeShortlistRepository,
)
from umbral.application.criteria.contracts import (
    Compilation,
    CompiledCriterion,
    ListingObservation,
)
from umbral.application.radar.contracts import RecommendationItem, RecommendationRun
from umbral.application.scoring.service import ScoringService
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import (
    load_explanations_templates,
    load_scoring_policy_seed,
)

SEED = load_scoring_policy_seed()
TEMPLATES = load_explanations_templates()
MATCHER_TYPES = load_matcher_types()


class ScoringTestContext:
    def __init__(self, comparator_enabled: bool = False) -> None:
        self.policies = FakePolicyRepository()
        self.evaluations = FakeEvaluationRepository()
        self.observations = FakeObservationReader()
        self.compilations = FakeCompilationReader()
        self.runs = FakeRunReader()
        self.items = FakeItemReader()
        self.profiles = FakeProfileReader()
        self.listings = FakeListingReader()
        self.shortlists = FakeShortlistRepository() if comparator_enabled else None
        self.service = ScoringService(
            policies=self.policies,
            evaluations=self.evaluations,
            observations=self.observations,
            compilations=self.compilations,
            runs=self.runs,
            items=self.items,
            profiles=self.profiles,
            listings=self.listings,
            shortlists=self.shortlists,
            matcher_types=MATCHER_TYPES,
            policy_seed=SEED,
            policy_seed_version="scoring-policy-v1",
            templates=TEMPLATES,
            legacy_score_policy_version="scoring-baseline-v1",
            comparison_max_listings=6,
            comparator_enabled=comparator_enabled,
            clock=lambda: datetime.now(timezone.utc),
        )


def build_compilation(
    *,
    profile_id: UUID,
    profile_version_id: UUID,
    criteria: tuple[CompiledCriterion, ...],
) -> Compilation:
    return Compilation(
        compilation_id=uuid4(),
        profile_id=profile_id,
        profile_version_id=profile_version_id,
        compilation_version=1,
        criteria=criteria,
        warnings=(),
        confirmations=(),
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def build_criterion(
    concept_key: str,
    matcher_type: str = "categorical",
    params: dict[str, object] | None = None,
    weight: float | None = None,
) -> CompiledCriterion:
    return CompiledCriterion(
        concept_key=concept_key,
        matcher_type=matcher_type,  # type: ignore[arg-type]
        params=params or {},
        source_ref="fact:test",
        soft_to_hard=False,
        weight=weight,
    )


def build_observation(
    *,
    listing_id: UUID,
    concept_key: str,
    value: object,
    confidence: float = 1.0,
    score: float = 1.0,
) -> ListingObservation:
    return ListingObservation(
        observation_id=uuid4(),
        listing_id=listing_id,
        concept_key=concept_key,
        matcher_type="categorical",
        value=value,
        score=score,
        confidence=confidence,
        evidence={"fragment": "evidencia", "span": None, "matched_on": []},
        source="rule",
        extraction_version_id=uuid4(),
        state="active",
        failure_code=None,
        recomputation_run_id=None,
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def build_run(
    *,
    profile_id: UUID,
    profile_version_id: UUID,
    score_policy_version: str = "scoring-policy-v1",
    state: str = "succeeded",
    run_id: UUID | None = None,
) -> RecommendationRun:
    return RecommendationRun(
        run_id=run_id or uuid4(),
        profile_id=profile_id,
        profile_version_id=profile_version_id,
        state=state,  # type: ignore[arg-type]
        trigger="created",
        score_policy_version=score_policy_version,
        candidate_count=1,
        published_item_count=1,
        failure_code=None,
        job_execution_id=None,
        created_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
        version=1,
    )


def build_item(
    run_id: UUID, listing_id: UUID, position: int = 0, score: float = 0.7
) -> RecommendationItem:
    return RecommendationItem(
        item_id=uuid4(),
        run_id=run_id,
        listing_id=listing_id,
        score=score,
        position=position,
        contributions={},
    )
