"""Composition helper for the radar application service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from umbral.application.jobs.ports import JobRuntime
from umbral.application.radar.service import RadarService
from umbral.application.scoring.engine import PolicyRunEngine
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyCandidateListingReader,
    SqlAlchemyEventRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyListingReader,
    SqlAlchemyProfileVersionRepository,
    SqlAlchemyRunRepository,
    SqlAlchemySearchProfileRepository,
)
from umbral.infrastructure.radar.contract_loader import (
    load_events_registry,
    load_scoring_baseline,
    load_search_profile_policy,
)

SessionFactory = Callable[[], Any]


def build_radar_service(
    *,
    session_factory: SessionFactory,
    job_runtime: JobRuntime | None,
    run_job_type: str = "recommendation.run",
    score_policy_version: str = "scoring-baseline-v1",
    policy_engine: PolicyRunEngine | None = None,
    clock: Callable[[], datetime] | None = None,
) -> RadarService:
    policy = load_search_profile_policy()
    scoring = load_scoring_baseline()
    events_registry = load_events_registry()
    return RadarService(
        profiles=SqlAlchemySearchProfileRepository(session_factory),
        versions=SqlAlchemyProfileVersionRepository(session_factory),
        runs=SqlAlchemyRunRepository(session_factory),
        items=SqlAlchemyItemRepository(session_factory),
        events=SqlAlchemyEventRepository(session_factory),
        candidates=SqlAlchemyCandidateListingReader(session_factory),
        listings=SqlAlchemyListingReader(session_factory),
        policy=policy,
        scoring=scoring,
        events_registry=events_registry,
        job_runtime=job_runtime,
        run_job_type=run_job_type,
        score_policy_version=score_policy_version,
        policy_engine=policy_engine,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )
