"""Application ports for the structured search radar."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
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


class SearchProfileRepository(Protocol):
    def insert(self, profile: SearchProfile) -> None: ...

    def insert_with_version(
        self,
        profile: SearchProfile,
        version: ProfileVersion,
        created_event: ProductEvent,
    ) -> None:
        """Atomically insert profile, snapshot, current pointer and audit event."""
        ...

    def get(self, profile_id: UUID) -> SearchProfile | None: ...

    def list_by_owner(
        self, owner_id: UUID, status: SearchProfileState | None
    ) -> tuple[SearchProfile, ...]: ...

    def save(self, profile: SearchProfile) -> None: ...

    def save_with_version(
        self, profile: SearchProfile, version: ProfileVersion
    ) -> None:
        """Atomically apply an optimistic profile update and its snapshot."""
        ...


class ProfileVersionRepository(Protocol):
    def insert(self, version: ProfileVersion) -> None: ...

    def get(self, version_id: UUID) -> ProfileVersion | None: ...

    def latest_for_profile(self, profile_id: UUID) -> ProfileVersion | None: ...


class RunRepository(Protocol):
    def insert(self, run: RecommendationRun) -> None: ...

    def reserve(self, run: RecommendationRun) -> RecommendationRun:
        """Insert one durable intent or return the existing unique run."""
        ...

    def bind_job(
        self, run_id: UUID, job_execution_id: UUID
    ) -> RecommendationRun:
        """Bind a durable reservation to its idempotent job execution."""
        ...

    def get(self, run_id: UUID) -> RecommendationRun | None: ...

    def get_for_version(
        self, profile_id: UUID, profile_version_id: UUID
    ) -> RecommendationRun | None: ...

    def get_reserved(
        self, profile_id: UUID, profile_version_id: UUID, trigger: str
    ) -> RecommendationRun | None: ...

    def latest_for_profile(self, profile_id: UUID) -> RecommendationRun | None: ...

    def latest_succeeded_for_profile(
        self, profile_id: UUID
    ) -> RecommendationRun | None: ...

    def exists(
        self, profile_id: UUID, profile_version_id: UUID, trigger: str
    ) -> bool: ...

    def publish(
        self,
        run: RecommendationRun,
        items: tuple[RecommendationItem, ...],
        event: ProductEvent,
        evaluations: tuple[CriterionEvaluation, ...] = (),
    ) -> None: ...

    def fail(self, run: RecommendationRun, failure_code: str) -> None: ...


class ItemRepository(Protocol):
    def list_for_run(
        self, run_id: UUID, after_position: int | None, limit: int
    ) -> tuple[RecommendationItem, ...]: ...

    def listing_ids_for_run(self, run_id: UUID) -> tuple[UUID, ...]: ...

    def listing_accessible(self, owner_id: UUID, listing_id: UUID) -> bool: ...


class EventRepository(Protocol):
    def insert(self, event: ProductEvent) -> None: ...


class CandidateListingReader(Protocol):
    """Reads Silver listings that can pass the profile's hard filters."""

    def list_candidates(
        self,
        profile: SearchProfile,
        *,
        supported_neighborhoods: tuple[str, ...],
        supported_property_types: tuple[str, ...],
    ) -> tuple[NormalizedListing, ...]: ...


class ListingReader(Protocol):
    """Reads Silver listings by id for detail assembly."""

    def get(self, listing_id: UUID) -> NormalizedListing | None: ...

    def changes_for_listing(
        self, listing_id: UUID
    ) -> tuple[Mapping[str, object], ...]: ...


class Clock(Protocol):
    def __call__(self) -> datetime: ...
