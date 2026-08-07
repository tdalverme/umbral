"""Composition helper for the scoring service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from umbral.application.scoring.service import ScoringService
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyItemRepository,
    SqlAlchemyRunRepository,
    SqlAlchemySearchProfileRepository,
)
from umbral.infrastructure.db.repositories.scoring import (
    SqlAlchemyEvaluationRepository,
    SqlAlchemyObservationReader,
    SqlAlchemyPolicyRepository,
    SqlAlchemyScoringListingReader,
    SqlAlchemyShortlistRepository,
)
from umbral.infrastructure.scoring.contract_loader import (
    load_explanations_templates,
    load_scoring_policy_seed,
)

SessionFactory = Callable[[], Any]


def build_scoring_service(
    *,
    session_factory: SessionFactory,
    policy_seed_version: str = "scoring-policy-v1",
    legacy_score_policy_version: str = "scoring-baseline-v1",
    comparison_max_listings: int = 6,
    comparator_enabled: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> ScoringService:
    return ScoringService(
        policies=SqlAlchemyPolicyRepository(session_factory),
        evaluations=SqlAlchemyEvaluationRepository(session_factory),
        observations=SqlAlchemyObservationReader(session_factory),
        compilations=_CompilationReaderAdapter(session_factory),
        runs=SqlAlchemyRunRepository(session_factory),
        items=SqlAlchemyItemRepository(session_factory),
        profiles=SqlAlchemySearchProfileRepository(session_factory),
        listings=SqlAlchemyScoringListingReader(session_factory),
        shortlists=(
            SqlAlchemyShortlistRepository(session_factory)
            if comparator_enabled
            else None
        ),
        matcher_types=load_matcher_types(),
        policy_seed=load_scoring_policy_seed(),
        policy_seed_version=policy_seed_version,
        templates=load_explanations_templates(),
        legacy_score_policy_version=legacy_score_policy_version,
        comparison_max_listings=comparison_max_listings,
        comparator_enabled=comparator_enabled,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )


class _CompilationReaderAdapter:
    """Exposes the criteria compilation repository as the scoring port."""

    def __init__(self, session_factory: SessionFactory) -> None:
        from umbral.infrastructure.db.repositories.criteria import (
            SqlAlchemyCompilationRepository,
        )

        self._inner = SqlAlchemyCompilationRepository(session_factory)

    def latest_for_profile_version(self, profile_version_id: Any) -> Any:
        return self._inner.latest_for_profile_version(profile_version_id)
