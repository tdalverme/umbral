"""In-memory adapters for the scoring ports (unit tests and local runtime)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.criteria.contracts import Compilation, ListingObservation
from umbral.application.radar.contracts import (
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.scoring.contracts import CriterionEvaluation, PolicyVersion
from umbral.application.silver.contracts import NormalizedListing


@dataclass
class FakePolicyRepository:
    rows: dict[str, list[PolicyVersion]] = field(default_factory=dict)

    def register_version(
        self,
        *,
        policy_key: str,
        policy_version: int,
        contract_version: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
        now: datetime,
    ) -> PolicyVersion:
        version = PolicyVersion(
            version_id=UUID(int=0x1000 + policy_version),
            policy_id=UUID(int=0x1001),
            policy_version=policy_version,
            contract_version=contract_version,
            payload=dict(payload),
            created_at=now,
            correlation_id=correlation_id,
        )
        self.rows.setdefault(policy_key, []).append(version)
        return version

    def latest_version(self, policy_key: str) -> PolicyVersion | None:
        versions = self.rows.get(policy_key, ())
        return max(versions, key=lambda item: item.policy_version) if versions else None

    def get_version(self, version_id: UUID) -> PolicyVersion | None:
        for versions in self.rows.values():
            for version in versions:
                if version.version_id == version_id:
                    return version
        return None


@dataclass
class FakeEvaluationRepository:
    rows: list[CriterionEvaluation] = field(default_factory=list)

    def insert_many(self, evaluations: tuple[CriterionEvaluation, ...]) -> None:
        self.rows.extend(evaluations)

    def for_run(self, run_id: UUID) -> tuple[CriterionEvaluation, ...]:
        return tuple(item for item in self.rows if item.run_id == run_id)

    def for_run_and_listings(
        self, run_id: UUID, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, tuple[CriterionEvaluation, ...]]:
        by_listing: dict[UUID, list[CriterionEvaluation]] = {}
        for item in self.rows:
            if item.run_id == run_id and item.listing_id in listing_ids:
                by_listing.setdefault(item.listing_id, []).append(item)
        return {listing_id: tuple(items) for listing_id, items in by_listing.items()}


@dataclass
class FakeShortlistRepository:
    rows: dict[UUID, list[UUID]] = field(default_factory=dict)

    def replace(
        self,
        *,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
        now: datetime,
        correlation_id: UUID,
    ) -> None:
        del now, correlation_id
        self.rows[profile_id] = list(listing_ids)

    def list_for_profile(self, profile_id: UUID) -> tuple[UUID, ...]:
        return tuple(self.rows.get(profile_id, ()))


@dataclass
class FakeObservationReader:
    observations: Mapping[UUID, Mapping[str, ListingObservation]] = field(
        default_factory=dict
    )

    def active_for_listings(
        self, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, Mapping[str, ListingObservation]]:
        return {
            listing_id: dict(self.observations.get(listing_id, {}))
            for listing_id in listing_ids
        }


@dataclass
class FakeCompilationReader:
    compilations: dict[UUID, Compilation] = field(default_factory=dict)

    def latest_for_profile_version(
        self, profile_version_id: UUID
    ) -> Compilation | None:
        return self.compilations.get(profile_version_id)


@dataclass
class FakeRunReader:
    rows: dict[UUID, RecommendationRun] = field(default_factory=dict)

    def get(self, run_id: UUID) -> RecommendationRun | None:
        return self.rows.get(run_id)

    def latest_succeeded_for_profile(
        self, profile_id: UUID
    ) -> RecommendationRun | None:
        values = [
            run
            for run in self.rows.values()
            if run.profile_id == profile_id and run.state == "succeeded"
        ]
        return max(values, key=lambda item: item.created_at) if values else None


@dataclass
class FakeItemReader:
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


@dataclass
class FakeProfileReader:
    rows: dict[UUID, SearchProfile] = field(default_factory=dict)

    def get(self, profile_id: UUID) -> SearchProfile | None:
        return self.rows.get(profile_id)


@dataclass
class FakeListingReader:
    rows: dict[UUID, NormalizedListing] = field(default_factory=dict)

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        return self.rows.get(listing_id)

    def list_by_ids(
        self, listing_ids: tuple[UUID, ...]
    ) -> tuple[NormalizedListing, ...]:
        return tuple(
            self.rows.get(listing_id)
            for listing_id in listing_ids
            if listing_id in self.rows
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
