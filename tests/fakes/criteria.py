"""In-memory adapters for the criteria ports (unit tests and local runtime)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from uuid import UUID

from umbral.application.criteria.contracts import (
    Compilation,
    Concept,
    ConceptVersion,
    ExtractionVersion,
    ListingObservation,
    PreferenceFact,
    RecomputeRun,
    RecomputeScope,
)
from umbral.application.events.contracts import ProductEvent
from umbral.application.silver.contracts import NormalizedListing


@dataclass
class FakeConceptRepository:
    rows: dict[str, Concept] = field(default_factory=dict)
    versions: list[ConceptVersion] = field(default_factory=list)

    def insert(self, concept: Concept) -> None:
        self.rows[concept.key] = concept

    def save(self, concept: Concept) -> None:
        self.rows[concept.key] = concept

    def get(self, key: str) -> Concept | None:
        return self.rows.get(key)

    def list_active(self) -> tuple[Concept, ...]:
        return tuple(sorted(self.rows.values(), key=lambda item: item.key))

    def insert_version(self, version: ConceptVersion) -> None:
        self.versions.append(version)

    def latest_version(self, concept_id: UUID) -> ConceptVersion | None:
        matches = [
            version for version in self.versions if version.concept_id == concept_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.concept_version)


@dataclass
class FakeFactRepository:
    rows: list[PreferenceFact] = field(default_factory=list)

    def record_change(self, fact: PreferenceFact, superseded_by: UUID | None) -> None:
        if superseded_by is not None:
            for index, existing in enumerate(self.rows):
                if (
                    existing.profile_id == fact.profile_id
                    and existing.concept_key == fact.concept_key
                    and existing.state == "active"
                ):
                    self.rows[index] = replace(
                        existing, state="superseded", superseded_by=superseded_by
                    )
        self.rows.append(fact)

    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceFact, ...]:
        return tuple(
            fact
            for fact in self.rows
            if fact.profile_id == profile_id and fact.state == "active"
        )

    def supersede_active(
        self,
        profile_id: UUID,
        concept_key: str,
        *,
        superseded_by: UUID | None,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
    ) -> int:
        count = 0
        for index, existing in enumerate(self.rows):
            if (
                existing.profile_id == profile_id
                and existing.concept_key == concept_key
                and existing.state == "active"
            ):
                self.rows[index] = replace(
                    existing,
                    state="superseded",
                    superseded_by=superseded_by,
                )
                count += 1
        return count


@dataclass
class FakeCompilationRepository:
    rows: list[Compilation] = field(default_factory=list)

    def insert(self, compilation: Compilation) -> None:
        self.rows.append(compilation)

    def latest_for_profile_version(
        self, profile_version_id: UUID
    ) -> Compilation | None:
        matches = [
            item for item in self.rows if item.profile_version_id == profile_version_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.compilation_version)


@dataclass
class FakeExtractionVersionRepository:
    rows: list[ExtractionVersion] = field(default_factory=list)

    def insert(self, version: ExtractionVersion) -> None:
        self.rows.append(version)

    def get(self, version_id: UUID) -> ExtractionVersion | None:
        return next((item for item in self.rows if item.version_id == version_id), None)

    def find(self, kind: str, key: str, version: str) -> ExtractionVersion | None:
        return next(
            (
                item
                for item in self.rows
                if item.kind == kind and item.key == key and item.version == version
            ),
            None,
        )

    def latest(self, kind: str, key: str) -> ExtractionVersion | None:
        matches = [item for item in self.rows if item.kind == kind and item.key == key]
        if not matches:
            return None
        return max(matches, key=lambda item: item.created_at)


@dataclass
class FakeObservationRepository:
    rows: list[ListingObservation] = field(default_factory=list)
    published: list[tuple[tuple[ListingObservation, ...], tuple[UUID, ...]]] = field(
        default_factory=list
    )
    recompute_runs: "FakeRecomputeRunRepository | None" = None
    events: "FakeEventRepository | None" = None

    def invalidate_for_concept(self, concept_key: str) -> int:
        count = 0
        for index, observation in enumerate(self.rows):
            if observation.concept_key == concept_key and observation.state == "active":
                self.rows[index] = replace(observation, state="invalidated")
                count += 1
        return count

    def invalidate_for_extraction_version(self, extraction_version_id: UUID) -> int:
        count = 0
        for index, observation in enumerate(self.rows):
            if (
                observation.extraction_version_id == extraction_version_id
                and observation.state == "active"
            ):
                self.rows[index] = replace(observation, state="invalidated")
                count += 1
        return count

    def invalidate_for_normalizer_version(self, normalizer_version: str) -> int:
        count = 0
        for index, observation in enumerate(self.rows):
            if observation.state == "active":
                self.rows[index] = replace(observation, state="invalidated")
                count += 1
        return count

    def ids_for_scope(self, scope: RecomputeScope) -> tuple[UUID, ...]:
        return tuple(
            observation.observation_id
            for observation in self.rows
            if observation.state in {"active", "invalidated"}
            and (
                scope.kind == "full"
                or (scope.kind == "concept" and observation.concept_key == scope.key)
                or (
                    scope.kind == "extraction"
                    and observation.extraction_version_id == UUID(scope.key)
                )
            )
        )

    def publish(
        self,
        observations: tuple[ListingObservation, ...],
        supersede_ids: tuple[UUID, ...],
        run: RecomputeRun | None,
        event: ProductEvent | None,
    ) -> None:
        for index, observation in enumerate(self.rows):
            if observation.observation_id in supersede_ids:
                self.rows[index] = replace(observation, state="superseded")
        self.rows.extend(observations)
        self.published.append((observations, supersede_ids))
        if run is not None and self.recompute_runs is not None:
            self.recompute_runs.rows[run.run_id] = run
        if event is not None and self.events is not None:
            self.events.events.append(event)


@dataclass
class FakeRecomputeRunRepository:
    rows: dict[UUID, RecomputeRun] = field(default_factory=dict)

    def insert(self, run: RecomputeRun) -> None:
        self.rows[run.run_id] = run

    def get(self, run_id: UUID) -> RecomputeRun | None:
        return self.rows.get(run_id)

    def fail(self, run: RecomputeRun, failure_code: str) -> None:
        self.rows[run.run_id] = replace(run, state="failed")


@dataclass
class FakeUrbanSignalRepository:
    signals: dict[UUID, list[Mapping[str, object]]] = field(default_factory=dict)

    def insert(self, signal: Mapping[str, object]) -> None:
        listing_id = signal["listing_id"]
        self.signals.setdefault(listing_id, []).append(signal)

    def list_for_listing(
        self, listing_id: UUID
    ) -> tuple[Mapping[str, object], ...]:
        return tuple(self.signals.get(listing_id, ()))


@dataclass
class FakeEventRepository:
    events: list[ProductEvent] = field(default_factory=list)

    def insert(self, event: ProductEvent) -> None:
        self.events.append(event)


@dataclass
class FakeListingReader:
    listings: dict[UUID, NormalizedListing] = field(default_factory=dict)

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        return self.listings.get(listing_id)

    def list_all(self) -> tuple[NormalizedListing, ...]:
        return tuple(self.listings.values())

    def list_by_normalizer_version(
        self, normalizer_version: str
    ) -> tuple[NormalizedListing, ...]:
        return tuple(
            listing
            for listing in self.listings.values()
            if listing.normalizer_version == normalizer_version
        )


@dataclass
class FakeProfileSnapshotReader:
    payloads: dict[UUID, Mapping[str, object]] = field(default_factory=dict)
    versions: dict[UUID, tuple[UUID, int]] = field(default_factory=dict)
    owners: dict[UUID, UUID] = field(default_factory=dict)

    def get_payload(self, profile_version_id: UUID) -> Mapping[str, object] | None:
        return self.payloads.get(profile_version_id)

    def get_version(self, profile_version_id: UUID) -> tuple[UUID, int] | None:
        return self.versions.get(profile_version_id)

    def owner_of(self, profile_id: UUID) -> UUID | None:
        return self.owners.get(profile_id)
