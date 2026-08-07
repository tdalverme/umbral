"""Composition helper for the feedback service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast

from umbral.application.criteria.contracts import PreferenceFact
from umbral.application.criteria.registry import ConceptLike
from umbral.application.criteria.service import CriteriaService
from umbral.application.feedback.reasons import parse_quick_reasons
from umbral.application.feedback.service import FeedbackService
from umbral.application.radar.service import RadarService
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyConceptRepository,
    SqlAlchemyFactRepository,
)
from umbral.infrastructure.db.repositories.feedback import (
    SqlAlchemyFeedbackEventRepository,
    SqlAlchemyLearningPolicyRepository,
    SqlAlchemyLearningProposalRepository,
)
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyEventRepository,
    SqlAlchemySearchProfileRepository,
)
from umbral.infrastructure.db.repositories.scoring import (
    SqlAlchemyScoringListingReader,
    SqlAlchemyShortlistRepository,
)
from umbral.infrastructure.feedback.contract_loader import (
    load_learning_policy_seed,
    load_quick_reasons_seed,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Any]


def build_feedback_service(
    *,
    session_factory: SessionFactory,
    policy_seed_version: str = "learning-v1",
    quick_reasons_seed_version: str = "quick-reasons-v1",
    free_feedback_enabled: bool = False,
    max_free_feedback_length: int = 500,
    radar: RadarService | None = None,
    criteria: CriteriaService | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FeedbackService:
    concepts_seed = load_concepts_seed()
    reasons_seed = load_quick_reasons_seed()
    reasons = parse_quick_reasons(
        reasons_seed, tuple(concept.key for concept in concepts_seed.concepts)
    )
    return FeedbackService(
        events=SqlAlchemyFeedbackEventRepository(session_factory),
        policies=SqlAlchemyLearningPolicyRepository(session_factory),
        proposals=SqlAlchemyLearningProposalRepository(session_factory),
        shortlists=SqlAlchemyShortlistRepository(session_factory),
        profiles=SqlAlchemySearchProfileRepository(session_factory),
        listings=SqlAlchemyScoringListingReader(session_factory),
        concepts=_ConceptReaderAdapter(session_factory),
        facts=_FactReaderAdapter(session_factory),
        events_out=SqlAlchemyEventRepository(session_factory),
        events_registry=load_events_registry(),
        reasons=reasons,
        policy_seed=load_learning_policy_seed(),
        policy_seed_version=policy_seed_version,
        free_feedback_enabled=free_feedback_enabled,
        max_free_feedback_length=max_free_feedback_length,
        radar=radar,
        criteria=criteria,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )


class _ConceptReaderAdapter:
    """Exposes the criteria concept repository as the feedback concept port."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._inner = SqlAlchemyConceptRepository(session_factory)

    def get(self, concept_key: str) -> tuple[Any, str] | None:
        concept = self._inner.get(concept_key)
        if concept is None:
            return None
        return concept.concept_id, cast(ConceptLike, concept).key


class _FactReaderAdapter:
    """Exposes the criteria fact repository as the feedback fact port."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._inner = SqlAlchemyFactRepository(session_factory)

    def active_for_profile(self, profile_id: Any) -> tuple[PreferenceFact, ...]:
        return self._inner.active_for_profile(profile_id)
