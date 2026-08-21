"""Application ports for the feedback domain; infrastructure supplies adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.criteria.contracts import PreferenceFact
from umbral.application.events.contracts import ProductEvent
from umbral.application.feedback.contracts import (
    FeedbackEvent,
    LearningPolicyVersion,
    LearningProposal,
)
from umbral.application.radar.contracts import SearchProfile
from umbral.application.silver.contracts import NormalizedListing


class FeedbackEventRepository(Protocol):
    def record(
        self, event: FeedbackEvent, superseded: FeedbackEvent | None
    ) -> FeedbackEvent: ...

    def get_by_idempotency(
        self, profile_id: UUID, idempotency_key: str
    ) -> FeedbackEvent | None: ...

    def active_state(
        self, profile_id: UUID, listing_id: UUID
    ) -> FeedbackEvent | None: ...

    def active_for_profile(self, profile_id: UUID) -> tuple[FeedbackEvent, ...]: ...

    def signal_events_since(
        self, profile_id: UUID, concept_id: UUID, since: datetime
    ) -> tuple[FeedbackEvent, ...]: ...

    def list_for_profile(
        self,
        profile_id: UUID,
        decision_state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[FeedbackEvent, ...], int | None]: ...


class LearningPolicyRepository(Protocol):
    def register_version(
        self,
        *,
        policy_key: str,
        policy_version: int,
        contract_version: str,
        payload: object,
        correlation_id: UUID,
        now: datetime,
    ) -> LearningPolicyVersion: ...

    def latest_version(self, policy_key: str) -> LearningPolicyVersion | None: ...

    def get_version(self, version_id: UUID) -> LearningPolicyVersion | None: ...


class LearningProposalRepository(Protocol):
    def insert(self, proposal: LearningProposal) -> LearningProposal: ...

    def get(self, proposal_id: UUID) -> LearningProposal | None: ...

    def pending_for_concept(
        self, profile_id: UUID, concept_id: UUID
    ) -> LearningProposal | None: ...

    def recent_for_concept(
        self, profile_id: UUID, concept_id: UUID, since: datetime
    ) -> tuple[LearningProposal, ...]: ...

    def list_for_profile(
        self,
        profile_id: UUID,
        state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[LearningProposal, ...], int | None]: ...

    def update(self, proposal: LearningProposal) -> LearningProposal: ...


class ShortlistPort(Protocol):
    def add(
        self,
        profile_id: UUID,
        listing_id: UUID,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> None: ...

    def remove(self, profile_id: UUID, listing_id: UUID) -> None: ...

    def list_for_profile(self, profile_id: UUID) -> tuple[UUID, ...]: ...


class ProfileReader(Protocol):
    def get(self, profile_id: UUID) -> SearchProfile | None: ...


class ListingReader(Protocol):
    def get(self, listing_id: UUID) -> NormalizedListing | None: ...

    def list_by_ids(
        self, listing_ids: tuple[UUID, ...]
    ) -> tuple[NormalizedListing, ...]: ...


class ConceptReader(Protocol):
    def get(self, concept_key: str) -> tuple[UUID, str] | None: ...

    def is_computable(self, concept_key: str) -> bool: ...


class FactReader(Protocol):
    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceFact, ...]: ...


class EventWriter(Protocol):
    def insert(self, event: ProductEvent) -> None: ...
