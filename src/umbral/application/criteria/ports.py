"""Application ports for the criteria domain; infrastructure supplies adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
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


class ConceptRepository(Protocol):
    def insert(self, concept: Concept) -> None: ...

    def save(self, concept: Concept) -> None: ...

    def get(self, key: str) -> Concept | None: ...

    def list_active(self) -> tuple[Concept, ...]: ...

    def insert_version(self, version: ConceptVersion) -> None: ...

    def latest_version(self, concept_id: UUID) -> ConceptVersion | None: ...


class FactRepository(Protocol):
    def record_change(
        self, fact: PreferenceFact, superseded_by: UUID | None
    ) -> None: ...

    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceFact, ...]: ...

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
        """Mark the active fact of (profile, concept) as superseded without a
        replacement (preference removal); returns the count superseded."""


class CompilationRepository(Protocol):
    def insert(self, compilation: Compilation) -> None: ...

    def latest_for_profile_version(
        self, profile_version_id: UUID
    ) -> Compilation | None: ...


class ExtractionVersionRepository(Protocol):
    def insert(self, version: ExtractionVersion) -> None: ...

    def get(self, version_id: UUID) -> ExtractionVersion | None: ...

    def find(self, kind: str, key: str, version: str) -> ExtractionVersion | None: ...

    def latest(self, kind: str, key: str) -> ExtractionVersion | None: ...


class ObservationRepository(Protocol):
    def invalidate_for_concept(self, concept_key: str) -> int: ...

    def invalidate_for_extraction_version(self, extraction_version_id: UUID) -> int: ...

    def invalidate_for_normalizer_version(self, normalizer_version: str) -> int: ...

    def ids_for_scope(self, scope: RecomputeScope) -> tuple[UUID, ...]: ...

    def publish(
        self,
        observations: tuple[ListingObservation, ...],
        supersede_ids: tuple[UUID, ...],
        run: RecomputeRun | None,
        event: ProductEvent | None,
    ) -> None: ...


class RecomputeRunRepository(Protocol):
    def insert(self, run: RecomputeRun) -> None: ...

    def get(self, run_id: UUID) -> RecomputeRun | None: ...

    def fail(self, run: RecomputeRun, failure_code: str) -> None: ...


class EmbeddingRepository(Protocol):
    def publish_embeddings(
        self,
        listing_ids: tuple[UUID, ...],
        extraction_version_id: UUID,
        vectors: Mapping[UUID, tuple[float, ...]],
        run: RecomputeRun | None,
    ) -> None: ...

    def active_versions_for_listing(self, listing_id: UUID) -> tuple[UUID, ...]: ...


class UrbanSignalRepository(Protocol):
    def insert(self, signal: Mapping[str, object]) -> None: ...

    def list_for_listing(
        self, listing_id: UUID
    ) -> tuple[Mapping[str, object], ...]: ...


class ListingProjectionReader(Protocol):
    """Reads Silver listings as extraction projections by id or scope."""

    def get(self, listing_id: UUID) -> NormalizedListing | None: ...

    def list_all(self) -> tuple[NormalizedListing, ...]: ...

    def list_by_normalizer_version(
        self, normalizer_version: str
    ) -> tuple[NormalizedListing, ...]: ...


class ProfileSnapshotReader(Protocol):
    """Reads search profile versions and their owner for criteria compilation."""

    def get_payload(self, profile_version_id: UUID) -> Mapping[str, object] | None: ...

    def get_version(self, profile_version_id: UUID) -> tuple[UUID, int] | None: ...

    def owner_of(self, profile_id: UUID) -> UUID | None: ...


class EventRepository(Protocol):
    def insert(self, event: ProductEvent) -> None: ...
