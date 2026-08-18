"""Shared Postgres backend and seeding for feedback integration tests."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection

from umbral.application.criteria.service import CriteriaService
from umbral.application.feedback.service import FeedbackService
from umbral.application.radar.contracts import SearchProfile
from umbral.application.radar.service import RadarService
from umbral.application.scoring.engine import PolicyRunEngine
from umbral.infrastructure.feedback.composition import build_feedback_service

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def feedback_backend(request: pytest.FixtureRequest) -> SessionFactory:
    """Postgres at head for one feedback integration test."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory


def build_feedback(
    factory: SessionFactory,
    *,
    free_feedback_enabled: bool = False,
    radar: object | None = None,
    criteria: object | None = None,
) -> FeedbackService:
    service = build_feedback_service(
        session_factory=factory,
        policy_seed_version="learning-v1",
        quick_reasons_seed_version="quick-reasons-v1",
        free_feedback_enabled=free_feedback_enabled,
        radar=radar,  # type: ignore[arg-type]
        criteria=criteria,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    service.seed_policy_registry(correlation_id=uuid4())
    return service


def seed_user(factory: SessionFactory) -> UUID:
    from tests.integration.radar.conftest import seed_user as _seed_user

    from umbral.infrastructure.db.repositories.radar import (
        SqlAlchemySearchProfileRepository,
    )

    del SqlAlchemySearchProfileRepository
    return _seed_user(factory)


def seed_concepts(factory: SessionFactory) -> None:
    """Seed the concept registry so concept-linked reasons resolve ids."""
    from uuid import uuid4

    from umbral.infrastructure.criteria.composition import build_criteria_service

    criteria = build_criteria_service(session_factory=factory, job_runtime=None)
    criteria.seed_registry(correlation_id=uuid4())


def build_criteria(factory: SessionFactory) -> CriteriaService:
    from umbral.infrastructure.criteria.composition import build_criteria_service

    return build_criteria_service(session_factory=factory, job_runtime=None)


def build_radar(factory: SessionFactory, scoring: PolicyRunEngine | None = None) -> RadarService:
    from umbral.application.jobs.service import InMemoryJobRuntime
    from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
    from umbral.infrastructure.radar.composition import build_radar_service

    return build_radar_service(
        session_factory=factory,
        job_runtime=InMemoryJobRuntime(queue=RecordingJobQueue()),
        policy_engine=scoring,
        score_policy_version="scoring-baseline-v1",
        clock=lambda: _NOW,
    )


def seed_profile(factory: SessionFactory, owner_id: UUID) -> SearchProfile:
    from tests.support.radar import build_profile

    from umbral.application.radar.contracts import ProfileVersion
    from umbral.infrastructure.db.repositories.radar import (
        SqlAlchemyProfileVersionRepository,
        SqlAlchemySearchProfileRepository,
    )

    profile = build_profile(owner_id=owner_id, name="Mi radar")
    SqlAlchemySearchProfileRepository(factory).insert(profile)
    version = ProfileVersion(
        version_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version=1,
        payload={},
        created_at=_NOW,
        correlation_id=uuid4(),
    )
    SqlAlchemyProfileVersionRepository(factory).insert(version)
    return profile
