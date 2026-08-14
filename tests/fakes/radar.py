"""In-memory adapters for the radar ports, used by unit tests and the local runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from threading import RLock
from typing import Protocol
from uuid import UUID

from umbral.application.events.contracts import ProductEvent
from umbral.application.radar.contracts import (
    ProfileVersion,
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
    SearchProfileState,
)
from umbral.application.scoring.contracts import CriterionEvaluation
from umbral.application.silver.contracts import NormalizedListing
from umbral.domain.errors import ConcurrencyConflict


@dataclass
class FakeSearchProfileRepository:
    rows: dict[UUID, SearchProfile] = field(default_factory=dict)
    version_rows: dict[UUID, ProfileVersion] = field(default_factory=dict)
    fail_next_atomic_save: bool = False
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def insert(self, profile: SearchProfile) -> None:
        self.rows[profile.profile_id] = profile

    def insert_with_version(
        self, profile: SearchProfile, version: ProfileVersion
    ) -> None:
        with self._lock:
            if profile.profile_id in self.rows or self._version_exists(version):
                raise ConcurrencyConflict(
                    expected_version=profile.version,
                    actual_version=self._actual_version(profile.profile_id),
                )
            self._validate_snapshot_pointer(profile, version)
            self.rows[profile.profile_id] = profile
            self.version_rows[version.version_id] = version

    def get(self, profile_id: UUID) -> SearchProfile | None:
        return self.rows.get(profile_id)

    def list_by_owner(
        self, owner_id: UUID, status: SearchProfileState | None
    ) -> tuple[SearchProfile, ...]:
        values = [
            profile
            for profile in self.rows.values()
            if profile.owner_id == owner_id
            and (status is None or profile.status == status)
        ]
        return tuple(sorted(values, key=lambda item: item.created_at, reverse=True))

    def save(self, profile: SearchProfile) -> None:
        current = self.rows.get(profile.profile_id)
        if current is None:
            raise KeyError(profile.profile_id)
        if current.version != profile.version:
            raise ConcurrencyConflict(
                expected_version=profile.version, actual_version=current.version
            )
        self.rows[profile.profile_id] = replace(profile, version=current.version + 1)

    def save_with_version(
        self, profile: SearchProfile, version: ProfileVersion
    ) -> None:
        with self._lock:
            current = self.rows.get(profile.profile_id)
            if current is None:
                raise KeyError(profile.profile_id)
            if self.fail_next_atomic_save:
                self.fail_next_atomic_save = False
                raise ConcurrencyConflict(
                    expected_version=profile.version,
                    actual_version=current.version,
                )
            if current.version != profile.version or self._version_exists(version):
                raise ConcurrencyConflict(
                    expected_version=profile.version,
                    actual_version=current.version,
                )
            self._validate_snapshot_pointer(profile, version)
            self.rows[profile.profile_id] = replace(
                profile, version=current.version + 1
            )
            self.version_rows[version.version_id] = version

    def _actual_version(self, profile_id: UUID) -> int | None:
        profile = self.rows.get(profile_id)
        return profile.version if profile is not None else None

    def _version_exists(self, version: ProfileVersion) -> bool:
        return version.version_id in self.version_rows or any(
            existing.profile_id == version.profile_id
            and existing.profile_version == version.profile_version
            for existing in self.version_rows.values()
        )

    @staticmethod
    def _validate_snapshot_pointer(
        profile: SearchProfile, version: ProfileVersion
    ) -> None:
        if (
            profile.current_version_id != version.version_id
            or profile.profile_id != version.profile_id
        ):
            raise ValueError("profile current version must reference its snapshot")


@dataclass
class FakeProfileVersionRepository:
    rows: dict[UUID, ProfileVersion] = field(default_factory=dict)

    def insert(self, version: ProfileVersion) -> None:
        self.rows[version.version_id] = version

    def get(self, version_id: UUID) -> ProfileVersion | None:
        return self.rows.get(version_id)

    def latest_for_profile(self, profile_id: UUID) -> ProfileVersion | None:
        matches = [
            version
            for version in self.rows.values()
            if version.profile_id == profile_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.profile_version)


@dataclass
class FakeRunRepository:
    rows: dict[UUID, RecommendationRun] = field(default_factory=dict)
    events: list[ProductEvent] = field(default_factory=list)
    items_by_run: dict[UUID, list[RecommendationItem]] = field(default_factory=dict)
    evaluations_by_run: dict[UUID, list[CriterionEvaluation]] = field(
        default_factory=dict
    )
    fail_next_bind: bool = False
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def insert(self, run: RecommendationRun) -> None:
        self.rows[run.run_id] = run
        self.items_by_run.setdefault(run.run_id, [])

    def reserve(self, run: RecommendationRun) -> RecommendationRun:
        with self._lock:
            existing = next(
                (
                    current
                    for current in self.rows.values()
                    if current.profile_id == run.profile_id
                    and current.profile_version_id == run.profile_version_id
                    and current.trigger == run.trigger
                ),
                None,
            )
            if existing is not None:
                return existing
            self.rows[run.run_id] = run
            self.items_by_run.setdefault(run.run_id, [])
            return run

    def bind_job(
        self, run_id: UUID, job_execution_id: UUID
    ) -> RecommendationRun:
        with self._lock:
            current = self.rows.get(run_id)
            if current is None:
                raise KeyError(run_id)
            if current.job_execution_id is not None:
                if current.job_execution_id == job_execution_id:
                    return current
                raise ConcurrencyConflict(
                    expected_version=current.version,
                    actual_version=current.version,
                )
            if self.fail_next_bind:
                self.fail_next_bind = False
                raise RuntimeError("bind unavailable")
            bound = replace(
                current,
                job_execution_id=job_execution_id,
                version=current.version + 1,
            )
            self.rows[run_id] = bound
            return bound

    def get(self, run_id: UUID) -> RecommendationRun | None:
        return self.rows.get(run_id)

    def latest_for_profile(self, profile_id: UUID) -> RecommendationRun | None:
        values = [run for run in self.rows.values() if run.profile_id == profile_id]
        if not values:
            return None
        return max(values, key=lambda item: item.created_at)

    def get_for_version(
        self, profile_id: UUID, profile_version_id: UUID
    ) -> RecommendationRun | None:
        matches = [
            run
            for run in self.rows.values()
            if run.profile_id == profile_id
            and run.profile_version_id == profile_version_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.created_at)

    def get_reserved(
        self, profile_id: UUID, profile_version_id: UUID, trigger: str
    ) -> RecommendationRun | None:
        return next(
            (
                run
                for run in self.rows.values()
                if run.profile_id == profile_id
                and run.profile_version_id == profile_version_id
                and run.trigger == trigger
            ),
            None,
        )

    def latest_succeeded_for_profile(
        self, profile_id: UUID
    ) -> RecommendationRun | None:
        values = [
            run
            for run in self.rows.values()
            if run.profile_id == profile_id and run.state == "succeeded"
        ]
        if not values:
            return None
        return max(values, key=lambda item: item.created_at)

    def exists(self, profile_id: UUID, profile_version_id: UUID, trigger: str) -> bool:
        return any(
            run.profile_id == profile_id
            and run.profile_version_id == profile_version_id
            and run.trigger == trigger
            for run in self.rows.values()
        )

    def publish(
        self,
        run: RecommendationRun,
        items: tuple[RecommendationItem, ...],
        event: ProductEvent,
        evaluations: tuple[CriterionEvaluation, ...] = (),
    ) -> None:
        current = self.rows.get(run.run_id)
        if current is None:
            raise KeyError(run.run_id)
        if current.version != run.version:
            raise ConcurrencyConflict(
                expected_version=run.version, actual_version=current.version
            )
        self.rows[run.run_id] = RecommendationRun(
            run_id=run.run_id,
            profile_id=run.profile_id,
            profile_version_id=run.profile_version_id,
            state="succeeded",
            trigger=run.trigger,
            score_policy_version=run.score_policy_version,
            candidate_count=run.candidate_count,
            published_item_count=len(items),
            failure_code=None,
            job_execution_id=run.job_execution_id,
            created_at=run.created_at,
            finished_at=event.occurred_at,
            correlation_id=run.correlation_id,
            version=current.version + 1,
        )
        self.items_by_run[run.run_id] = list(items)
        self.events.append(event)
        if evaluations:
            self.evaluations_by_run.setdefault(run.run_id, []).extend(evaluations)

    def fail(self, run: RecommendationRun, failure_code: str) -> None:
        current = self.rows.get(run.run_id)
        if current is None:
            raise KeyError(run.run_id)
        if current.version != run.version:
            raise ConcurrencyConflict(
                expected_version=run.version, actual_version=current.version
            )
        self.rows[run.run_id] = RecommendationRun(
            run_id=run.run_id,
            profile_id=run.profile_id,
            profile_version_id=run.profile_version_id,
            state="failed",
            trigger=run.trigger,
            score_policy_version=run.score_policy_version,
            candidate_count=run.candidate_count,
            published_item_count=0,
            failure_code=failure_code,
            job_execution_id=run.job_execution_id,
            created_at=run.created_at,
            finished_at=None,
            correlation_id=run.correlation_id,
            version=current.version + 1,
        )


@dataclass
class FakeItemRepository:
    items_by_run: dict[UUID, list[RecommendationItem]] = field(default_factory=dict)

    def list_for_run(
        self, run_id: UUID, after_position: int | None, limit: int
    ) -> tuple[RecommendationItem, ...]:
        items = sorted(
            self.items_by_run.get(run_id, ()), key=lambda item: item.position
        )
        if after_position is not None:
            items = [item for item in items if item.position > after_position]
        return tuple(items[:limit])

    def listing_ids_for_run(self, run_id: UUID) -> tuple[UUID, ...]:
        return tuple(item.listing_id for item in self.items_by_run.get(run_id, ()))

    def listing_accessible(self, owner_id: UUID, listing_id: UUID) -> bool:
        del owner_id
        return any(
            item.listing_id == listing_id
            for items in self.items_by_run.values()
            for item in items
        )


@dataclass
class FakeEventRepository:
    events: list[ProductEvent] = field(default_factory=list)

    def insert(self, event: ProductEvent) -> None:
        self.events.append(event)


@dataclass
class FakeCandidateListingReader:
    listings: list[NormalizedListing] = field(default_factory=list)

    def list_candidates(
        self,
        profile: SearchProfile,
        *,
        supported_neighborhoods: tuple[str, ...],
    ) -> tuple[NormalizedListing, ...]:
        del profile, supported_neighborhoods
        return tuple(self.listings)


class HasListingId(Protocol):
    listing_id: UUID


@dataclass
class FakeListingReader:
    listings: dict[UUID, NormalizedListing] = field(default_factory=dict)

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        return self.listings.get(listing_id)

    def changes_for_listing(self, listing_id: UUID) -> tuple[Mapping[str, object], ...]:
        del listing_id
        return ()
