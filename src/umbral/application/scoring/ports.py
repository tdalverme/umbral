"""Application ports for the scoring domain; infrastructure supplies adapters."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.criteria.contracts import Compilation, ListingObservation
from umbral.application.radar.contracts import (
    ProfileVersion,
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.scoring.contracts import CriterionEvaluation, PolicyVersion
from umbral.application.silver.contracts import NormalizedListing


class PolicyRepository(Protocol):
    def register_version(
        self,
        *,
        policy_key: str,
        policy_version: int,
        contract_version: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
        now: datetime,
    ) -> PolicyVersion: ...

    def latest_version(self, policy_key: str) -> PolicyVersion | None: ...

    def get_version(self, version_id: UUID) -> PolicyVersion | None: ...


class EvaluationRepository(Protocol):
    def insert_many(self, evaluations: tuple[CriterionEvaluation, ...]) -> None: ...

    def for_run(self, run_id: UUID) -> tuple[CriterionEvaluation, ...]: ...

    def for_run_and_listings(
        self, run_id: UUID, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, tuple[CriterionEvaluation, ...]]: ...


class ShortlistRepository(Protocol):
    def replace(
        self,
        *,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
        now: datetime,
        correlation_id: UUID,
    ) -> None: ...

    def list_for_profile(self, profile_id: UUID) -> tuple[UUID, ...]: ...


class ObservationReader(Protocol):
    def active_for_listings(
        self, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, Mapping[str, ListingObservation]]: ...


class CompilationReader(Protocol):
    def latest_for_profile_version(
        self, profile_version_id: UUID
    ) -> Compilation | None: ...


class RunReader(Protocol):
    def get(self, run_id: UUID) -> RecommendationRun | None: ...

    def latest_succeeded_for_profile(
        self, profile_id: UUID
    ) -> RecommendationRun | None: ...


class ItemReader(Protocol):
    def list_for_run(
        self, run_id: UUID, after_position: int | None, limit: int
    ) -> tuple[RecommendationItem, ...]: ...

    def listing_ids_for_run(self, run_id: UUID) -> tuple[UUID, ...]: ...


class ProfileReader(Protocol):
    def get(self, profile_id: UUID) -> SearchProfile | None: ...


class ProfileVersionReader(Protocol):
    def get(self, version_id: UUID) -> ProfileVersion | None: ...


class ListingReader(Protocol):
    def get(self, listing_id: UUID) -> NormalizedListing | None: ...

    def list_by_ids(
        self, listing_ids: tuple[UUID, ...]
    ) -> tuple[NormalizedListing, ...]: ...
