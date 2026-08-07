"""In-memory adapters for the feedback ports (unit tests and local runtime)."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from umbral.application.criteria.contracts import PreferenceFact
from umbral.application.events.contracts import ProductEvent
from umbral.application.feedback.contracts import (
    FeedbackEvent,
    LearningPolicyVersion,
    LearningProposal,
)
from umbral.application.radar.contracts import SearchProfile
from umbral.application.silver.contracts import NormalizedListing


@dataclass
class FakeFeedbackEventRepository:
    rows: list[FeedbackEvent] = field(default_factory=list)

    def record(
        self, event: FeedbackEvent, superseded: FeedbackEvent | None
    ) -> FeedbackEvent:
        if superseded is not None:
            self.rows = [
                _supersede(item, event.event_id) if item.event_id == superseded.event_id else item
                for item in self.rows
            ]
        self.rows.append(event)
        return event

    def get_by_idempotency(
        self, profile_id: UUID, idempotency_key: str
    ) -> FeedbackEvent | None:
        for item in self.rows:
            if (
                item.profile_id == profile_id
                and item.idempotency_key == idempotency_key
            ):
                return item
        return None

    def active_state(
        self, profile_id: UUID, listing_id: UUID
    ) -> FeedbackEvent | None:
        for item in self.rows:
            if (
                item.profile_id == profile_id
                and item.listing_id == listing_id
                and item.state == "active"
            ):
                return item
        return None

    def active_for_profile(self, profile_id: UUID) -> tuple[FeedbackEvent, ...]:
        return tuple(
            item for item in self.rows if item.profile_id == profile_id and item.state == "active"
        )

    def signal_events_since(
        self, profile_id: UUID, concept_id: UUID, since: datetime
    ) -> tuple[FeedbackEvent, ...]:
        del concept_id, since
        return tuple(
            item for item in self.rows if item.profile_id == profile_id and item.state == "active"
        )

    def list_for_profile(
        self,
        profile_id: UUID,
        decision_state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[FeedbackEvent, ...], int | None]:
        items = [
            item
            for item in self.rows
            if item.profile_id == profile_id
            and item.state == "active"
            and (decision_state is None or item.event_type == decision_state)
        ]
        items.sort(key=lambda item: (item.created_at, item.event_id), reverse=True)
        page = tuple(items[(after or 0) : (after or 0) + limit])
        next_after = (after or 0) + len(page) if len(page) == limit else None
        return page, next_after


@dataclass
class FakeLearningPolicyRepository:
    rows: dict[str, list[LearningPolicyVersion]] = field(default_factory=dict)

    def register_version(
        self,
        *,
        policy_key: str,
        policy_version: int,
        contract_version: str,
        payload: object,
        correlation_id: UUID,
        now: datetime,
    ) -> LearningPolicyVersion:
        version = LearningPolicyVersion(
            version_id=uuid4(),
            policy_id=uuid4(),
            policy_version=policy_version,
            contract_version=contract_version,
            payload=dict(cast(Mapping[str, object], payload)),
            created_at=now,
            correlation_id=correlation_id,
        )
        self.rows.setdefault(policy_key, []).append(version)
        return version

    def latest_version(self, policy_key: str) -> LearningPolicyVersion | None:
        versions = self.rows.get(policy_key, ())
        return max(versions, key=lambda item: item.policy_version) if versions else None

    def get_version(self, version_id: UUID) -> LearningPolicyVersion | None:
        for versions in self.rows.values():
            for version in versions:
                if version.version_id == version_id:
                    return version
        return None


@dataclass
class FakeLearningProposalRepository:
    rows: list[LearningProposal] = field(default_factory=list)

    def insert(self, proposal: LearningProposal) -> LearningProposal:
        self.rows.append(proposal)
        return proposal

    def get(self, proposal_id: UUID) -> LearningProposal | None:
        for item in self.rows:
            if item.proposal_id == proposal_id:
                return item
        return None

    def pending_for_concept(
        self, profile_id: UUID, concept_id: UUID
    ) -> LearningProposal | None:
        for item in self.rows:
            if (
                item.profile_id == profile_id
                and item.concept_id == concept_id
                and item.state == "pending"
            ):
                return item
        return None

    def recent_for_concept(
        self, profile_id: UUID, concept_id: UUID, since: datetime
    ) -> tuple[LearningProposal, ...]:
        return tuple(
            item
            for item in self.rows
            if item.profile_id == profile_id
            and item.concept_id == concept_id
            and item.created_at >= since
        )

    def list_for_profile(
        self,
        profile_id: UUID,
        state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[LearningProposal, ...], int | None]:
        items = [
            item
            for item in self.rows
            if item.profile_id == profile_id
            and (state is None or item.state == state)
        ]
        items.sort(key=lambda item: (item.created_at, item.proposal_id), reverse=True)
        page = tuple(items[(after or 0) : (after or 0) + limit])
        next_after = (after or 0) + len(page) if len(page) == limit else None
        return page, next_after

    def update(self, proposal: LearningProposal) -> LearningProposal:
        self.rows = [
            proposal if item.proposal_id == proposal.proposal_id else item
            for item in self.rows
        ]
        return proposal


@dataclass
class FakeShortlistPort:
    rows: dict[UUID, list[UUID]] = field(default_factory=dict)

    def add(
        self,
        profile_id: UUID,
        listing_id: UUID,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> None:
        del now, correlation_id
        current = self.rows.setdefault(profile_id, [])
        if listing_id not in current:
            current.append(listing_id)

    def remove(self, profile_id: UUID, listing_id: UUID) -> None:
        self.rows[profile_id] = [
            item for item in self.rows.get(profile_id, ()) if item != listing_id
        ]

    def list_for_profile(self, profile_id: UUID) -> tuple[UUID, ...]:
        return tuple(self.rows.get(profile_id, ()))


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
        found: list[NormalizedListing] = []
        for listing_id in listing_ids:
            listing = self.rows.get(listing_id)
            if listing is not None:
                found.append(listing)
        return tuple(found)


@dataclass
class FakeConceptReader:
    rows: dict[str, UUID] = field(default_factory=dict)

    def get(self, concept_key: str) -> tuple[UUID, str] | None:
        concept_id = self.rows.get(concept_key)
        return (concept_id, concept_key) if concept_id is not None else None


@dataclass
class FakeFactReader:
    facts: tuple[PreferenceFact, ...] = field(default_factory=tuple)

    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceFact, ...]:
        del profile_id
        return self.facts


@dataclass
class FakeEventWriter:
    events: list[ProductEvent] = field(default_factory=list)

    def insert(self, event: ProductEvent) -> None:
        self.events.append(event)


def _supersede(event: FeedbackEvent, superseded_by: UUID) -> FeedbackEvent:
    from dataclasses import replace

    return replace(event, state="superseded", superseded_by=superseded_by)
