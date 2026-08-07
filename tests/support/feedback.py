"""Shared builder for feedback service unit tests with in-memory adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5

from tests.fakes.feedback import (
    FakeConceptReader,
    FakeEventWriter,
    FakeFactReader,
    FakeFeedbackEventRepository,
    FakeLearningPolicyRepository,
    FakeLearningProposalRepository,
    FakeListingReader,
    FakeProfileReader,
    FakeShortlistPort,
)
from tests.support.radar import build_profile
from umbral.application.feedback.reasons import parse_quick_reasons
from umbral.application.feedback.service import FeedbackService
from umbral.application.radar.contracts import SearchProfile
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed
from umbral.infrastructure.feedback.contract_loader import (
    load_learning_policy_seed,
    load_quick_reasons_seed,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry


class FeedbackTestContext:
    def __init__(
        self,
        *,
        free_feedback_enabled: bool = False,
        radar: object | None = None,
        criteria: object | None = None,
        max_free_feedback_length: int = 500,
    ) -> None:
        concepts_seed = load_concepts_seed()
        self.reasons = parse_quick_reasons(
            load_quick_reasons_seed(),
            tuple(concept.key for concept in concepts_seed.concepts),
        )
        self.events = FakeFeedbackEventRepository()
        self.policies = FakeLearningPolicyRepository()
        self.proposals = FakeLearningProposalRepository()
        self.shortlists = FakeShortlistPort()
        self.profiles = FakeProfileReader()
        self.listings = FakeListingReader()
        self.concepts = FakeConceptReader(
            rows={
                concept.key: uuid5(
                    uuid4(), f"concept:{concept.key}"
                )
                for concept in concepts_seed.concepts
            }
        )
        self.facts = FakeFactReader()
        self.events_out = FakeEventWriter()
        self.service = FeedbackService(
            events=self.events,
            policies=self.policies,
            proposals=self.proposals,
            shortlists=self.shortlists,
            profiles=self.profiles,
            listings=self.listings,
            concepts=self.concepts,
            facts=self.facts,
            events_out=self.events_out,
            events_registry=load_events_registry(),
            reasons=self.reasons,
            policy_seed=load_learning_policy_seed(),
            policy_seed_version="learning-v1",
            free_feedback_enabled=free_feedback_enabled,
            max_free_feedback_length=max_free_feedback_length,
            radar=radar,  # type: ignore[arg-type]
            criteria=criteria,  # type: ignore[arg-type]
            clock=lambda: NOW,
        )

    def add_profile(self, *, owner_id: UUID | None = None) -> SearchProfile:
        owner = owner_id or uuid4()
        profile = build_profile(owner_id=owner, name="Mi radar")
        self.profiles.rows[profile.profile_id] = profile
        return profile


NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
