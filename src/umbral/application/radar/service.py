"""Orchestration for the structured search radar.

The service owns profile lifecycle (create, list, get, update, status),
versioned snapshots, async run submission and publication, stable match
paging and listing detail assembly. Runs are executed by the durable
``recommendation.run`` job; a failed run never replaces the last valid one and
the run's publication (run success + items + run-published event) is atomic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import (
    EventsRegistrySpec,
    event_version,
    validate_event,
)
from umbral.application.jobs.contracts import SubmitJob
from umbral.application.jobs.ports import JobRuntime
from umbral.application.radar.contracts import (
    ListingDetail,
    ListingNotAccessible,
    ListingSummary,
    MatchPage,
    MatchPoint,
    ProfileVersion,
    RadarNotAccessible,
    RadarPermanentError,
    RadarStateError,
    RadarTransientError,
    RadarValidationError,
    RecommendationItem,
    RecommendationRun,
    RecommendationRunTrigger,
    RunNotFound,
    SearchProfile,
    SearchProfileState,
)
from umbral.application.radar.diagnostics import build_diagnostics
from umbral.application.radar.hard_filters import (
    RESIDENTIAL_PROPERTY_TYPES,
    CandidateListing,
    apply_hard_filters,
)
from umbral.application.radar.ports import (
    CandidateListingReader,
    EventRepository,
    ItemRepository,
    ListingReader,
    ProfileVersionRepository,
    RunRepository,
    SearchProfileRepository,
)
from umbral.application.radar.profile_policy import (
    SearchProfilePolicySpec,
    can_transition,
    default_unknown_strategy,
    freeze_search_profile_policy,
    frozen_search_profile_policy,
    rehydrate_profile_version,
    validate_profile,
)
from umbral.application.radar.scoring import (
    ScorableListing,
    ScoringBaselineSpec,
    compute_score,
)
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    ScoringNotFound,
    ScoringValidationError,
)
from umbral.application.scoring.engine import PolicyRunEngine
from umbral.application.silver.contracts import NormalizedListing
from umbral.domain.audit import AuditActor
from umbral.domain.errors import ConcurrencyConflict

RADAR_RUN_JOB_TYPE = "recommendation.run"

Clock = Callable[[], datetime]


class RadarService:
    def __init__(
        self,
        *,
        profiles: SearchProfileRepository,
        versions: ProfileVersionRepository,
        runs: RunRepository,
        items: ItemRepository,
        events: EventRepository,
        candidates: CandidateListingReader,
        listings: ListingReader,
        policy: SearchProfilePolicySpec,
        scoring: ScoringBaselineSpec,
        events_registry: EventsRegistrySpec,
        job_runtime: JobRuntime | None,
        run_job_type: str = RADAR_RUN_JOB_TYPE,
        score_policy_version: str = "scoring-baseline-v1",
        policy_engine: PolicyRunEngine | None = None,
        decision_states: Callable[
            [UUID, UUID, tuple[UUID, ...]], Mapping[UUID, str]
        ]
        | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.profiles = profiles
        self.versions = versions
        self.runs = runs
        self.items = items
        self.events = events
        self.candidates = candidates
        self.listings = listings
        self.policy = policy
        self.scoring = scoring
        self.events_registry = events_registry
        self.job_runtime = job_runtime
        self.run_job_type = run_job_type
        self.score_policy_version = score_policy_version
        self.policy_engine = policy_engine
        self.decision_states = decision_states
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def bind_decision_states(
        self,
        reader: Callable[[UUID, UUID, tuple[UUID, ...]], Mapping[UUID, str]],
    ) -> None:
        """Wire the feedback decision-state overlay after composition (H3.3)."""

        self.decision_states = reader

    # ------------------------------------------------------------------
    # Profile lifecycle
    # ------------------------------------------------------------------

    def create_profile(
        self,
        *,
        owner_id: UUID,
        name: str,
        zones: tuple[str, ...],
        budget_max: float | None,
        budget_min: float | None,
        min_rooms: int | None,
        surface_min: float | None,
        surface_max: float | None,
        unknown_strategy: Mapping[str, str] | None,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, RecommendationRun | None]:
        payload = _payload(
            name=name,
            zones=zones,
            budget_max=budget_max,
            budget_min=budget_min,
            min_rooms=min_rooms,
            surface_min=surface_min,
            surface_max=surface_max,
            status="active",
        )
        self._validate(payload)
        strategy = (
            dict(unknown_strategy)
            if unknown_strategy is not None
            else dict(default_unknown_strategy(self.policy))
        )
        now = self.clock()
        profile = SearchProfile(
            profile_id=uuid4(),
            owner_id=owner_id,
            name=name,
            operation="rental",
            zones=zones,
            budget_max=(float(budget_max) if budget_max is not None else None),
            budget_min=(float(budget_min) if budget_min is not None else None),
            min_rooms=min_rooms,
            surface_min=(float(surface_min) if surface_min is not None else None),
            surface_max=(float(surface_max) if surface_max is not None else None),
            status="active",
            unknown_strategy=strategy,
            version=1,
            created_at=now,
            updated_at=now,
            current_version_id=None,
            latest_run_id=None,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        version = self._snapshot(profile, payload, profile_version=1)
        profile = replace(profile, current_version_id=version.version_id)
        created_event = self._server_event(
            event_type="radar.created.v1",
            actor_id=owner_id,
            correlation_id=correlation_id,
            payload={
                "search_profile_id": str(profile.profile_id),
                "profile_version": version.profile_version,
            },
        )
        self.profiles.insert_with_version(profile, version, created_event)
        run = self._schedule_after_commit(profile, version, trigger="created")
        return profile, run

    def list_profiles(
        self, owner_id: UUID, status: SearchProfileState | None
    ) -> tuple[SearchProfile, ...]:
        return self.profiles.list_by_owner(owner_id, status)

    def get_profile(self, owner_id: UUID, profile_id: UUID) -> SearchProfile:
        profile = self._owned(owner_id, profile_id)
        return profile

    def validate_change(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        changes: Mapping[str, object],
    ) -> SearchProfile:
        """Validate a proposed profile change without persisting (H4.2).

        Uses the exact same validation path as ``update_profile`` so a change
        that passes here can be applied later with the same guarantee; raises
        ``RadarValidationError``/``RadarStateError`` otherwise.
        """

        profile = self._owned(owner_id, profile_id)
        if profile.status == "archived":
            raise RadarStateError("archived profiles cannot be edited")
        current_payload = _payload_from_profile(profile)
        merged = dict(current_payload)
        merged.update(changes)
        self._validate(merged)
        return profile

    def profile_with_latest_run(
        self, owner_id: UUID, profile_id: UUID
    ) -> tuple[SearchProfile, RecommendationRun | None]:
        profile = self._owned(owner_id, profile_id)
        return profile, self.runs.latest_for_profile(profile_id)

    def latest_run_of(self, profile: SearchProfile) -> RecommendationRun | None:
        return self.runs.latest_for_profile(profile.profile_id)

    def update_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        changes: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, RecommendationRun | None]:
        profile, version = self.version_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            expected_version=expected_version,
            changes=changes,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        run = self._schedule_after_commit(profile, version, trigger="edited")
        return profile, run

    def version_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        changes: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, ProfileVersion]:
        profile = self._owned(owner_id, profile_id)
        self._check_version(profile, expected_version)
        if profile.status == "archived":
            raise RadarStateError("archived profiles cannot be edited")

        current_payload = _payload_from_profile(profile)
        merged = dict(current_payload)
        merged.update(changes)
        self._validate(merged)
        now = self.clock()
        raw_zones = merged["zones"]
        merged_name = str(merged["name"])
        merged_zones = (
            tuple(str(zone) for zone in raw_zones)
            if isinstance(raw_zones, list)
            else ()
        )
        merged_budget_max = _optional_number(merged.get("budget_max"))
        merged_budget_min = _optional_number(merged.get("budget_min"))
        merged_min_rooms = _optional_int(merged.get("min_rooms"))
        merged_surface_min = _optional_number(merged.get("surface_min"))
        merged_surface_max = _optional_number(merged.get("surface_max"))
        updated = replace(
            profile,
            name=merged_name,
            zones=merged_zones,
            budget_max=merged_budget_max,
            budget_min=merged_budget_min,
            min_rooms=merged_min_rooms,
            surface_min=merged_surface_min,
            surface_max=merged_surface_max,
            version=profile.version + 1,
            updated_at=now,
            actor_kind=actor_kind,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        current_version = self.versions.latest_for_profile(profile_id)
        next_profile_version = (
            current_version.profile_version + 1 if current_version is not None else 1
        )
        version = self._snapshot(updated, merged, profile_version=next_profile_version)
        self.profiles.save_with_version(
            replace(
                updated,
                current_version_id=version.version_id,
                version=profile.version,
            ),
            version,
        )
        updated = replace(updated, current_version_id=version.version_id)
        return updated, version

    def schedule_version_run(
        self,
        *,
        profile: SearchProfile,
        version: ProfileVersion,
        trigger: RecommendationRunTrigger,
    ) -> RecommendationRun | None:
        self._check_version_owner(profile, version)
        if profile.status != "active":
            return None
        return self._submit_run(profile, version, trigger)

    def set_status(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        status: SearchProfileState,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, RecommendationRun | None]:
        profile = self._owned(owner_id, profile_id)
        self._check_version(profile, expected_version)
        if not can_transition(self.policy, profile.status, status):
            raise RadarStateError(
                f"transition {profile.status} -> {status} is not allowed"
            )
        now = self.clock()
        updated = replace(
            profile,
            status=status,
            version=profile.version + 1,
            updated_at=now,
            actor_kind=actor_kind,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        self.profiles.save(replace(profile, status=status, updated_at=now))
        run = None
        if status == "active" and profile.status == "paused":
            current_version = self.versions.latest_for_profile(profile_id)
            if current_version is not None:
                run = self._schedule_after_commit(
                    updated, current_version, trigger="resumed"
                )
        return updated, run

    def bump_profile_version(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, ProfileVersion]:
        """Version and snapshot a profile without submitting a run.

        Used by the learning confirm/undo flow (H3.3): the caller records a
        preference fact and compiles against the new version before the run is
        submitted. Mirrors ``update_profile`` internals minus the edits path.
        """

        profile = self._owned(owner_id, profile_id)
        return self.version_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            expected_version=profile.version,
            changes={},
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )

    def submit_run(
        self,
        profile: SearchProfile,
        version: ProfileVersion,
        trigger: str = "edited",
    ) -> RecommendationRun | None:
        """Submit the existing recommendation.run job for a profile version."""

        return self._submit_run(profile, version, trigger)

    # ------------------------------------------------------------------
    # Matches and detail
    # ------------------------------------------------------------------

    def get_matches(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID | None,
        after_position: int | None,
        limit: int,
        include_dismissed: bool = False,
    ) -> MatchPage:
        self._owned(owner_id, profile_id)
        run = (
            self.runs.get(run_id)
            if run_id is not None
            else self.runs.latest_succeeded_for_profile(profile_id)
        )
        if run is None or run.profile_id != profile_id:
            if run_id is not None:
                raise RunNotFound(run_id)
            raise RunNotFound(profile_id)
        if run.state != "succeeded":
            return MatchPage(run=run, items=(), next_after_position=None)
        items = self.items.list_for_run(run.run_id, after_position, limit)
        listing_ids = tuple(item.listing_id for item in items)
        states: Mapping[UUID, str] = {}
        if self.decision_states is not None:
            states = self.decision_states(owner_id, profile_id, listing_ids)
        visible = tuple(
            item
            for item in items
            if include_dismissed or states.get(item.listing_id) != "dismiss"
        )
        next_after = visible[-1].position if len(visible) == limit else None
        points = tuple(
            MatchPoint(
                listing_id=item.listing_id,
                latitude=point[0],
                longitude=point[1],
                geo_precision=point[2],
            )
            for item in visible
            if (point := self._listing_point(item.listing_id)) is not None
        )
        summaries = tuple(
            ListingSummary(
                listing_id=item.listing_id,
                total_cost=summary[0],
                neighborhood=summary[1],
                surface_m2=summary[2],
                rooms=summary[3],
                source_id=summary[4],
                url=summary[5],
                geo_precision=summary[6],
            )
            for item in visible
            if (summary := self._listing_summary(item.listing_id)) is not None
        )
        return MatchPage(
            run=run,
            items=visible,
            next_after_position=next_after,
            points=points,
            summaries=summaries,
            decision_states={
                listing_id: state
                for listing_id, state in states.items()
                if listing_id in {item.listing_id for item in visible}
            },
        )

    def _listing_summary(
        self, listing_id: UUID
    ) -> (
        tuple[float, str | None, float | None, int | None, str, str | None, str] | None
    ):
        listing = self.listings.get(listing_id)
        if listing is None:
            return None
        return (
            listing.total_cost,
            listing.neighborhood,
            listing.surface_m2,
            listing.rooms,
            listing.source.source_id,
            listing.url,
            listing.geo_precision,
        )

    def _listing_point(self, listing_id: UUID) -> tuple[float, float, str] | None:
        listing = self.listings.get(listing_id)
        if listing is None or listing.geometry is None:
            return None
        if listing.geo_precision not in {"exact", "block"}:
            return None
        latitude, longitude = listing.geometry
        return latitude, longitude, listing.geo_precision

    def get_listing_detail(self, owner_id: UUID, listing_id: UUID) -> ListingDetail:
        if not self.items.listing_accessible(owner_id, listing_id):
            raise ListingNotAccessible(listing_id)
        listing = self.listings.get(listing_id)
        if listing is None:
            raise ListingNotAccessible(listing_id)
        changes = self.listings.changes_for_listing(listing_id)
        return ListingDetail(
            listing_id=listing.listing_id,
            source_id=listing.source.source_id,
            url=listing.url,
            neighborhood=listing.neighborhood,
            geo_precision=listing.geo_precision,
            total_cost=listing.total_cost,
            price_value=listing.price_value,
            price_currency=listing.price_currency,
            expenses_value=listing.expenses_value,
            surface_m2=listing.surface_m2,
            rooms=listing.rooms,
            bedrooms=listing.bedrooms,
            floor=listing.floor,
            property_type=listing.property_type,
            amenities=listing.amenities,
            description_text=listing.description_text,
            normalization_errors=listing.normalization_errors,
            known_changes=changes,
        )

    # ------------------------------------------------------------------
    # Run processing (called by the worker handler)
    # ------------------------------------------------------------------

    def process_run(
        self,
        *,
        run_id: UUID,
        job_execution_id: UUID | None,
    ) -> Mapping[str, object]:
        run = self.runs.get(run_id)
        if run is None:
            raise RadarPermanentError(
                "radar.run_not_found", "recommendation run is not visible"
            )
        profile_id = run.profile_id
        profile_version_id = run.profile_version_id
        profile = self.profiles.get(profile_id)
        if profile is None:
            raise RadarPermanentError(
                "radar.profile_not_found", "search profile is not visible"
            )
        if profile.profile_id != run.profile_id:
            raise RadarPermanentError(
                "radar.run_profile_mismatch",
                "recommendation run does not belong to the loaded profile",
            )
        version = self.versions.get(profile_version_id)
        if version is None:
            raise RadarPermanentError(
                "radar.version_not_found", "profile version is not visible"
            )
        if version.version_id != run.profile_version_id:
            raise RadarPermanentError(
                "radar.run_version_mismatch",
                "recommendation run does not reference the loaded profile version",
            )
        frozen_policy, residential_property_types = frozen_search_profile_policy(
            version
        )
        profile = rehydrate_profile_version(profile, version, frozen_policy)
        if run.state in {"succeeded", "failed", "superseded"}:
            return self._summary(run)

        current_run = self.runs.latest_succeeded_for_profile(profile_id)
        if (
            current_run is not None
            and current_run.profile_version_id != profile_version_id
        ):
            # A newer radar version already published; this run's results would
            # replace the current ones (FR-026/SC-012), so it is superseded.
            superseded = self.runs.supersede(
                run_id,
                reason="radar.results_superseded",
                correlation_id=run.correlation_id,
            )
            if superseded is not None:
                return self._summary(superseded)

        if job_execution_id is not None and run.job_execution_id is None:
            run = replace(run, job_execution_id=job_execution_id)

        candidates = self.candidates.list_candidates(
            profile,
            supported_neighborhoods=frozen_policy.neighborhoods,
            supported_property_types=residential_property_types,
        )
        passed = tuple(
            listing
            for listing in candidates
            if apply_hard_filters(
                cast(CandidateListing, listing),
                profile,
                supported_neighborhoods=frozen_policy.neighborhoods,
                supported_property_types=residential_property_types,
            )
        )
        if not passed:
            # Zero matches: persist diagnostics and offer relaxations (FR-021).
            hard_criteria = self._hard_criteria_from_compilation(profile_version_id)
            diagnostics = build_diagnostics(
                profile=profile,
                candidates=candidates,
                supported_neighborhoods=frozen_policy.neighborhoods,
                hard_criteria=hard_criteria,
            )
            run = self.runs.set_diagnostics(
                run_id,
                diagnostics=diagnostics,
                correlation_id=run.correlation_id,
            ) or run
        items: tuple[RecommendationItem, ...]
        evaluations: tuple[CriterionEvaluation, ...] = ()
        if run.score_policy_version != self.scoring.score_policy_version:
            if self.policy_engine is None:
                raise RadarPermanentError(
                    "radar.score_policy_not_found",
                    "run scoring policy is not available",
                )
            compilation = self.policy_engine.compilation_for(profile_version_id)
            if compilation is None:
                # Fallback a scoring baseline cuando la compilación aún no existe
                # (criteria aún no compiló la nueva versión). Evita dejar el run en pending
                # para siempre con radar.compilation_not_found y permite mostrar el mapa
                # con el último run sucedido mientras se genera la compilación.
                scored_fallback: list[tuple[float, NormalizedListing, Mapping[str, float]]] = []
                for listing in passed:
                    score, contributions = compute_score(
                        profile, cast(ScorableListing, listing), self.scoring
                    )
                    scored_fallback.append((score, listing, contributions))
                scored_fallback.sort(
                    key=lambda pair: (
                        -pair[0],
                        pair[1].total_cost,
                        str(pair[1].listing_id),
                    )
                )
                items = tuple(
                    RecommendationItem(
                        item_id=uuid4(),
                        run_id=run.run_id,
                        listing_id=listing.listing_id,
                        score=score,
                        position=position,
                        contributions={
                            "budget": contributions["budget"],
                            "rooms": contributions["rooms"],
                            "surface": contributions["surface"],
                            "location_precision": contributions["location_precision"],
                            "score_policy_version": run.score_policy_version,
                        },
                    )
                    for position, (score, listing, contributions) in enumerate(scored_fallback)
                )
                evaluations = ()
            else:
                try:
                    scored_v1 = self.policy_engine.score_run(
                        profile=profile,
                        compilation=compilation,
                        candidates=passed,
                        run_id=run.run_id,
                        correlation_id=run.correlation_id,
                        score_policy_version=run.score_policy_version,
                    )
                except (ScoringNotFound, ScoringValidationError) as error:
                    raise RadarPermanentError(
                        "radar.score_policy_not_found",
                        "run scoring policy is not available",
                    ) from error
                items = tuple(
                    RecommendationItem(
                        item_id=uuid4(),
                        run_id=run.run_id,
                        listing_id=candidate.listing_id,
                        score=candidate.score,
                        position=position,
                        contributions=dict(candidate.contributions),
                    )
                    for position, candidate in enumerate(scored_v1)
                )
                evaluations = tuple(
                    evaluation
                    for candidate in scored_v1
                    for evaluation in candidate.evaluations
                )
        else:
            scored: list[tuple[float, NormalizedListing, Mapping[str, float]]] = []
            for listing in passed:
                score, contributions = compute_score(
                    profile, cast(ScorableListing, listing), self.scoring
                )
                scored.append((score, listing, contributions))
            scored.sort(
                key=lambda pair: (
                    -pair[0],
                    pair[1].total_cost,
                    str(pair[1].listing_id),
                )
            )
            items = tuple(
                RecommendationItem(
                    item_id=uuid4(),
                    run_id=run.run_id,
                    listing_id=listing.listing_id,
                    score=score,
                    position=position,
                    contributions={
                        "budget": contributions["budget"],
                        "rooms": contributions["rooms"],
                        "surface": contributions["surface"],
                        "location_precision": contributions["location_precision"],
                        "score_policy_version": run.score_policy_version,
                    },
                )
                for position, (score, listing, contributions) in enumerate(scored)
            )
        now = self.clock()
        event = ProductEvent(
            event_id=uuid4(),
            event_type="recommendation.run_published.v1",
            event_version=1,
            actor_id=None,
            occurred_at=now,
            correlation_id=run.correlation_id,
            payload={
                "search_profile_id": str(profile_id),
                "run_id": str(run.run_id),
                "candidate_count": len(passed),
                "published_item_count": len(items),
                "score_policy_version": run.score_policy_version,
            },
        )
        try:
            published = replace(
                run,
                state="succeeded",
                candidate_count=len(passed),
                published_item_count=len(items),
                finished_at=now,
            )
            self.runs.publish(published, items, event, evaluations)
        except ConcurrencyConflict:
            raise RadarTransientError(
                "radar.run_race", "run publication lost the optimistic lock"
            ) from None
        return self._summary(published)

    # ------------------------------------------------------------------
    # Client events
    # ------------------------------------------------------------------

    def record_client_event(
        self,
        *,
        event_type: str,
        payload: Mapping[str, object],
        actor_id: UUID,
        correlation_id: UUID,
    ) -> ProductEvent:
        error = validate_event(self.events_registry, event_type, payload)
        if error is not None:
            raise RadarValidationError((error,))
        version = event_version(self.events_registry, event_type)
        event = ProductEvent(
            event_id=uuid4(),
            event_type=event_type,
            event_version=version or 1,
            actor_id=actor_id,
            occurred_at=self.clock(),
            correlation_id=correlation_id,
            payload=dict(payload),
        )
        self._emit_server_event(
            event_type=event_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            payload=dict(payload),
        )
        return event

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _owned(self, owner_id: UUID, profile_id: UUID) -> SearchProfile:
        profile = self.profiles.get(profile_id)
        if profile is None or profile.owner_id != owner_id:
            raise RadarNotAccessible(profile_id)
        return profile

    def _check_version(self, profile: SearchProfile, expected_version: int) -> None:
        if profile.version != expected_version:
            raise ConcurrencyConflict(
                expected_version=expected_version, actual_version=profile.version
            )

    def _validate(self, payload: Mapping[str, object]) -> None:
        errors = validate_profile(payload, self.policy)
        if errors:
            raise RadarValidationError(errors)

    def _snapshot(
        self,
        profile: SearchProfile,
        payload: Mapping[str, object],
        *,
        profile_version: int,
    ) -> ProfileVersion:
        version = ProfileVersion(
            version_id=uuid4(),
            profile_id=profile.profile_id,
            profile_version=profile_version,
            payload={
                **payload,
                "unknown_strategy": dict(profile.unknown_strategy),
                "search_profile_policy": freeze_search_profile_policy(
                    self.policy,
                    RESIDENTIAL_PROPERTY_TYPES,
                ),
            },
            created_at=self.clock(),
            correlation_id=profile.correlation_id,
            actor_kind=profile.actor_kind,
            actor_id=profile.actor_id,
        )
        return version

    def _submit_run(
        self, profile: SearchProfile, version: ProfileVersion, trigger: str
    ) -> RecommendationRun | None:
        self._check_version_owner(profile, version)
        if self.job_runtime is None:
            return None
        run = RecommendationRun(
            run_id=uuid4(),
            profile_id=profile.profile_id,
            profile_version_id=version.version_id,
            state="pending",
            trigger=cast(RecommendationRunTrigger, trigger),
            score_policy_version=self._pin_score_policy_version(),
            candidate_count=0,
            published_item_count=0,
            failure_code=None,
            job_execution_id=None,
            created_at=self.clock(),
            finished_at=None,
            correlation_id=profile.correlation_id,
            actor_kind=profile.actor_kind,
            actor_id=profile.actor_id,
        )
        run = self.runs.reserve(run)
        if run.job_execution_id is not None:
            return run
        job = self.job_runtime.submit(
            SubmitJob.create(
                job_type=self.run_job_type,
                logical_target=_job_target(run.run_id),
                idempotency_key=f"recommendation:{run.run_id}",
                correlation_id=profile.correlation_id,
                actor=AuditActor.system(),
            )
        )
        return self.runs.bind_job(run.run_id, job.execution_id)

    def _pin_score_policy_version(self) -> str:
        if self.policy_engine is not None:
            return self.policy_engine.pin_policy_version()
        if self.score_policy_version != self.scoring.score_policy_version:
            raise RadarStateError("loaded baseline scoring revision does not match")
        return self.score_policy_version

    @staticmethod
    def _check_version_owner(
        profile: SearchProfile, version: ProfileVersion
    ) -> None:
        if version.profile_id != profile.profile_id:
            raise RadarStateError("profile version does not belong to profile")

    def _schedule_after_commit(
        self,
        profile: SearchProfile,
        version: ProfileVersion,
        *,
        trigger: RecommendationRunTrigger,
    ) -> RecommendationRun | None:
        try:
            return self.schedule_version_run(
                profile=profile,
                version=version,
                trigger=trigger,
            )
        except Exception:
            try:
                return self.runs.get_reserved(
                    profile.profile_id,
                    version.version_id,
                    trigger,
                )
            except Exception:
                return None

    def _emit_server_event(
        self,
        *,
        event_type: str,
        actor_id: UUID | None,
        correlation_id: UUID,
        payload: Mapping[str, object],
    ) -> None:
        self.events.insert(
            self._server_event(
                event_type=event_type,
                actor_id=actor_id,
                correlation_id=correlation_id,
                payload=payload,
            )
        )

    def _server_event(
        self,
        *,
        event_type: str,
        actor_id: UUID | None,
        correlation_id: UUID,
        payload: Mapping[str, object],
    ) -> ProductEvent:
        version = event_version(self.events_registry, event_type)
        return ProductEvent(
            event_id=uuid4(),
            event_type=event_type,
            event_version=version or 1,
            actor_id=actor_id,
            occurred_at=self.clock(),
            correlation_id=correlation_id,
            payload=dict(payload),
        )

    @staticmethod
    def _summary(run: RecommendationRun) -> Mapping[str, object]:
        return {
            "run_id": str(run.run_id),
            "state": run.state,
            "candidate_count": run.candidate_count,
            "published_item_count": run.published_item_count,
            "failure_code": run.failure_code,
            "score_policy_version": run.score_policy_version,
        }

    def _hard_criteria_from_compilation(
        self, profile_version_id: UUID
    ) -> tuple[str, ...]:
        """Collect the confirmed concept-level hard criteria of a compilation."""
        if self.policy_engine is None:
            return ()
        compilation = self.policy_engine.compilation_for(profile_version_id)
        if compilation is None:
            return ()
        return tuple(
            criterion.concept_key
            for criterion in compilation.criteria
            if criterion.soft_to_hard
        )


def _payload(
    *,
    name: str,
    zones: tuple[str, ...],
    budget_max: float | None,
    budget_min: float | None,
    min_rooms: int | None,
    surface_min: float | None,
    surface_max: float | None,
    status: str,
) -> dict[str, object]:
    return {
        "name": name,
        "operation": "rental",
        "zones": list(zones),
        "budget_max": budget_max,
        "budget_min": budget_min,
        "min_rooms": min_rooms,
        "surface_min": surface_min,
        "surface_max": surface_max,
        "status": status,
    }


def _payload_from_profile(profile: SearchProfile) -> dict[str, object]:
    return _payload(
        name=profile.name,
        zones=profile.zones,
        budget_max=profile.budget_max,
        budget_min=profile.budget_min,
        min_rooms=profile.min_rooms,
        surface_min=profile.surface_min,
        surface_max=profile.surface_max,
        status=profile.status,
    )


def _job_target(run_id: UUID) -> str:
    return str(run_id)


def _optional_number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
