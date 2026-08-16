"""Orchestration for scoring v1, explanations and structured comparison.

The service owns policy versioning (append-only, validated documents), the
scoring v1 hook consumed by the radar run pipeline, deterministic on-demand
explanations, structured comparison with ownership checks, and the P1
persistent shortlist. Explanations and comparisons are read-only computations
over frozen run data; nothing is invented beyond the persisted breakdown.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.application.criteria.contracts import Compilation
from umbral.application.criteria.registry import MatcherTypesSpec
from umbral.application.radar.contracts import (
    RadarPermanentError,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.radar.profile_policy import (
    frozen_search_profile_policy,
    rehydrate_profile_version,
)
from umbral.application.scoring.comparison import EvaluationsByListing, build_comparison
from umbral.application.scoring.contracts import (
    Comparison,
    ComparisonDuplicateListing,
    ComparisonLimitExceeded,
    ComparisonNotInRadar,
    CriterionEvaluation,
    Explanation,
    ExplanationUnavailable,
    PolicyVersion,
    ScoringNotAccessible,
    ScoringNotFound,
    ScoringStateError,
    SemanticSignal,
)
from umbral.application.scoring.engine import (
    ScoredCandidate,
    score_candidates,
)
from umbral.application.scoring.explanations import build_explanation
from umbral.application.scoring.policy import ScoringPolicyDoc, parse_policy_document
from umbral.application.scoring.ports import (
    CompilationReader,
    EvaluationRepository,
    ItemReader,
    ListingReader,
    ObservationReader,
    PolicyRepository,
    ProfileReader,
    ProfileVersionReader,
    RunReader,
    SemanticSignalReader,
    ShortlistRepository,
)
from umbral.application.silver.contracts import NormalizedListing

Clock = Callable[[], datetime]

_LEGACY_POLICY = "scoring-baseline-v1"


class ScoringService:
    def __init__(
        self,
        *,
        policies: PolicyRepository,
        evaluations: EvaluationRepository,
        observations: ObservationReader,
        compilations: CompilationReader,
        runs: RunReader,
        items: ItemReader,
        profiles: ProfileReader,
        versions: ProfileVersionReader,
        listings: ListingReader,
        shortlists: ShortlistRepository | None,
        matcher_types: MatcherTypesSpec,
        policy_seed: Mapping[str, object],
        policy_seed_version: str,
        templates: Mapping[str, str],
        legacy_score_policy_version: str = _LEGACY_POLICY,
        comparison_max_listings: int = 6,
        comparator_enabled: bool = False,
        semantic_signals: SemanticSignalReader | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.policies = policies
        self.evaluations = evaluations
        self.observations = observations
        self.compilations = compilations
        self.runs = runs
        self.items = items
        self.profiles = profiles
        self.versions = versions
        self.listings = listings
        self.shortlists = shortlists
        self.matcher_types = matcher_types
        self.policy_seed = dict(policy_seed)
        self.policy_seed_version = policy_seed_version
        self.templates = templates
        self.legacy_score_policy_version = legacy_score_policy_version
        self.comparison_max_listings = comparison_max_listings
        self.comparator_enabled = comparator_enabled
        self.semantic_signals = semantic_signals
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Policy (US1)
    # ------------------------------------------------------------------

    def seed_registry(self, correlation_id: UUID) -> int:
        """Load the versioned policy seed idempotently; returns registered count."""

        if self.policies.latest_version(self.policy_seed_version) is not None:
            return 0
        self.register_policy_version(
            policy_key=self.policy_seed_version,
            payload=self.policy_seed,
            correlation_id=correlation_id,
        )
        return 1

    def register_policy_version(
        self,
        *,
        policy_key: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
    ) -> PolicyVersion:
        parsed = parse_policy_document(payload, self.matcher_types)
        latest = self.policies.latest_version(policy_key)
        policy_version = (latest.policy_version + 1) if latest is not None else 1
        return self.policies.register_version(
            policy_key=policy_key,
            policy_version=policy_version,
            contract_version=parsed.contract_version,
            payload=dict(payload),
            correlation_id=correlation_id,
            now=self.clock(),
        )

    def latest_policy_document(self) -> ScoringPolicyDoc:
        version = self._latest_policy_version()
        return parse_policy_document(version.payload, self.matcher_types)

    def pin_policy_version(self) -> str:
        version = self._latest_policy_version()
        parse_policy_document(version.payload, self.matcher_types)
        return str(version.version_id)

    # ------------------------------------------------------------------
    # Run scoring hook (US2, US3, US4)
    # ------------------------------------------------------------------

    def compilation_for(self, profile_version_id: UUID) -> Compilation | None:
        return self.compilations.latest_for_profile_version(profile_version_id)

    def score_run(
        self,
        *,
        profile: SearchProfile,
        compilation: Compilation,
        candidates: tuple[NormalizedListing, ...],
        run_id: UUID,
        correlation_id: UUID,
        score_policy_version: str,
    ) -> tuple[ScoredCandidate, ...]:
        policy = self._policy_document_for_reference(score_policy_version)
        observations = self.observations.active_for_listings(
            tuple(candidate.listing_id for candidate in candidates)
        )
        semantic_signals: Mapping[UUID, tuple[SemanticSignal, ...]] = {}
        if self.semantic_signals is not None:
            semantic_signals = self.semantic_signals.for_profile_version_and_listings(
                compilation.profile_version_id,
                tuple(candidate.listing_id for candidate in candidates),
            )
        return score_candidates(
            profile=profile,
            compilation=compilation,
            candidates=candidates,
            observations=observations,
            policy=policy,
            run_id=run_id,
            correlation_id=correlation_id,
            now=self.clock(),
            semantic_signals=semantic_signals,
        )

    # ------------------------------------------------------------------
    # Explanations (US6, US7)
    # ------------------------------------------------------------------

    def get_explanation(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID,
        listing_id: UUID,
    ) -> Explanation:
        run = self._owned_succeeded_run(owner_id, profile_id, run_id)
        if run.score_policy_version == self.legacy_score_policy_version:
            raise ExplanationUnavailable("this run has no breakdown data")
        listing_ids = self.items.listing_ids_for_run(run.run_id)
        if listing_id not in listing_ids:
            raise ScoringNotFound(f"listing not in run: {listing_id}")
        evaluations = self.evaluations.for_run_and_listings(
            run.run_id, (listing_id,)
        ).get(listing_id, ())
        item = next(
            (
                item
                for item in self.items.list_for_run(run.run_id, None, 1000)
                if item.listing_id == listing_id
            ),
            None,
        )
        if item is None:
            raise ScoringNotFound(f"listing not in run: {listing_id}")
        policy = self._policy_document_for_reference(run.score_policy_version)
        profile = self._profile_for_run(run)
        return build_explanation(
            search_profile_id=profile_id,
            run_id=run.run_id,
            listing_id=listing_id,
            score=item.score,
            confidence=_item_confidence(evaluations, policy),
            evaluations=evaluations,
            policy=policy,
            templates=self.templates,
            satisfied_filters=_satisfied_filters(profile),
            profile_version_id=run.profile_version_id,
        )

    def list_explanations(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID,
        after_position: int | None,
        limit: int,
    ) -> tuple[Explanation, ...]:
        run = self._owned_succeeded_run(owner_id, profile_id, run_id)
        if run.score_policy_version == self.legacy_score_policy_version:
            raise ExplanationUnavailable("this run has no breakdown data")
        items = self.items.list_for_run(run.run_id, after_position, limit)
        listing_ids = tuple(item.listing_id for item in items)
        evaluations_by_listing = self.evaluations.for_run_and_listings(
            run.run_id, listing_ids
        )
        policy = self._policy_document_for_reference(run.score_policy_version)
        profile = self._profile_for_run(run)
        return tuple(
            build_explanation(
                search_profile_id=profile_id,
                run_id=run.run_id,
                listing_id=item.listing_id,
                score=item.score,
                confidence=_item_confidence(
                    evaluations_by_listing.get(item.listing_id, ()), policy
                ),
                evaluations=evaluations_by_listing.get(item.listing_id, ()),
                policy=policy,
                templates=self.templates,
                satisfied_filters=_satisfied_filters(profile),
                profile_version_id=run.profile_version_id,
            )
            for item in items
        )

    # ------------------------------------------------------------------
    # Comparison (US8)
    # ------------------------------------------------------------------

    def build_comparison(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
    ) -> Comparison:
        run = self._owned_succeeded_run(
            owner_id, profile_id, self._latest_run_id(owner_id, profile_id)
        )
        if run.score_policy_version == self.legacy_score_policy_version:
            raise ExplanationUnavailable("this run has no breakdown data")
        if len(listing_ids) < 2:
            raise ComparisonLimitExceeded(self.comparison_max_listings)
        if len(set(listing_ids)) != len(listing_ids):
            raise ComparisonDuplicateListing()
        if len(listing_ids) > self.comparison_max_listings:
            raise ComparisonLimitExceeded(self.comparison_max_listings)
        run_listing_ids = self.items.listing_ids_for_run(run.run_id)
        outside = [item for item in listing_ids if item not in run_listing_ids]
        if outside:
            raise ComparisonNotInRadar(f"listing outside the run: {outside[0]}")
        items = self.items.list_for_run(run.run_id, None, 1000)
        evaluations: EvaluationsByListing = {
            listing_id: {
                evaluation.criterion_key: evaluation for evaluation in evaluations
            }
            for listing_id, evaluations in self.evaluations.for_run_and_listings(
                run.run_id, listing_ids
            ).items()
        }
        listings = {
            listing.listing_id: listing
            for listing in self.listings.list_by_ids(listing_ids)
        }
        policy = self._policy_document_for_reference(run.score_policy_version)
        profile = self._profile(profile_id)
        return build_comparison(
            profile=profile,
            run_id=run.run_id,
            score_version=policy.score_policy_version,
            limit=self.comparison_max_listings,
            items=items,
            listings_by_id=listings,
            evaluations=evaluations,
            policy=policy,
        )

    # ------------------------------------------------------------------
    # Shortlist (US10, P1)
    # ------------------------------------------------------------------

    def get_shortlist(self, *, owner_id: UUID, profile_id: UUID) -> tuple[UUID, ...]:
        self._profile_owned(owner_id, profile_id)
        if self.shortlists is None:
            return ()
        return self.shortlists.list_for_profile(profile_id)

    def set_shortlist(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
        correlation_id: UUID,
    ) -> tuple[UUID, ...]:
        self._profile_owned(owner_id, profile_id)
        if self.shortlists is None:
            raise ScoringStateError("comparator is not enabled")
        if len(listing_ids) > self.comparison_max_listings:
            raise ComparisonLimitExceeded(self.comparison_max_listings)
        run = self.runs.latest_succeeded_for_profile(profile_id)
        if run is None:
            raise ScoringNotFound(f"no published run for profile: {profile_id}")
        run_listing_ids = self.items.listing_ids_for_run(run.run_id)
        outside = [item for item in listing_ids if item not in run_listing_ids]
        if outside:
            raise ComparisonNotInRadar(f"listing outside the run: {outside[0]}")
        self.shortlists.replace(
            profile_id=profile_id,
            listing_ids=listing_ids,
            now=self.clock(),
            correlation_id=correlation_id,
        )
        return listing_ids

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _owned_succeeded_run(
        self, owner_id: UUID, profile_id: UUID, run_id: UUID
    ) -> RecommendationRun:
        self._profile_owned(owner_id, profile_id)
        run = self.runs.get(run_id)
        if run is None or run.profile_id != profile_id:
            raise ScoringNotFound(f"run not found: {run_id}")
        if run.state != "succeeded":
            raise ScoringStateError(f"run is not succeeded: {run.state}")
        return run

    def _latest_run_id(self, owner_id: UUID, profile_id: UUID) -> UUID:
        self._profile_owned(owner_id, profile_id)
        run = self.runs.latest_succeeded_for_profile(profile_id)
        if run is None:
            raise ScoringNotFound(f"no published run for profile: {profile_id}")
        return run.run_id

    def _profile_owned(self, owner_id: UUID, profile_id: UUID) -> SearchProfile:
        profile = self.profiles.get(profile_id)
        if profile is None or profile.owner_id != owner_id:
            raise ScoringNotAccessible(f"profile not accessible: {profile_id}")
        return profile

    def _profile(self, profile_id: UUID) -> SearchProfile:
        profile = self.profiles.get(profile_id)
        if profile is None:
            raise ScoringNotFound(f"profile not found: {profile_id}")
        return profile

    def _profile_for_run(self, run: RecommendationRun) -> SearchProfile:
        profile = self._profile(run.profile_id)
        version = self.versions.get(run.profile_version_id)
        if version is None or version.version_id != run.profile_version_id:
            raise ScoringNotFound(
                f"profile version not found: {run.profile_version_id}"
            )
        if version.profile_id != run.profile_id:
            raise ScoringStateError("profile version does not belong to run profile")
        try:
            frozen_policy, _ = frozen_search_profile_policy(version)
            return rehydrate_profile_version(
                profile,
                version,
                frozen_policy,
            )
        except RadarPermanentError as error:
            raise ScoringStateError(error.detail) from error

    def _latest_policy_version(self) -> PolicyVersion:
        version = self.policies.latest_version(self.policy_seed_version)
        if version is None:
            self.seed_registry(uuid4())
            version = self.policies.latest_version(self.policy_seed_version)
        if version is None:
            raise ScoringNotFound(
                f"no scoring policy registered: {self.policy_seed_version}"
            )
        return version

    def _policy_document_for_reference(self, reference: str) -> ScoringPolicyDoc:
        try:
            version_id = UUID(reference)
        except ValueError:
            raise ScoringNotFound(
                f"scoring policy version not found: {reference}"
            ) from None
        version = self.policies.get_version(version_id)
        if version is None:
            raise ScoringNotFound(
                f"scoring policy version not found: {reference}"
            )
        policy = parse_policy_document(version.payload, self.matcher_types)
        return replace(policy, score_policy_version=reference)


def _item_confidence(
    evaluations: tuple[CriterionEvaluation, ...], policy: ScoringPolicyDoc
) -> float:
    if not evaluations:
        return 0.0
    base = sum(item.confidence for item in evaluations) / len(evaluations)
    unknown_count = sum(1 for item in evaluations if item.state == "unknown")
    penalty = policy.confidence.get("unknown_penalty", 0.2)
    return round(max(0.0, base - penalty * unknown_count), 3)


def _satisfied_filters(profile: SearchProfile) -> tuple[str, ...]:
    filters: list[str] = []
    if profile.budget_max is not None and profile.budget_max > 0:
        filters.append("budget_max")
    if profile.zones:
        filters.append("zones")
    if profile.min_rooms is not None and profile.min_rooms > 0:
        filters.append("min_rooms")
    if profile.surface_min is not None or profile.surface_max is not None:
        filters.append("surface")
    return tuple(filters)
