"""Shared Postgres backend and Silver seeding for scoring integration tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection
from tests.support.radar import build_profile

from umbral.application.radar.service import RadarService
from umbral.application.scoring.service import ScoringService
from umbral.infrastructure.radar.composition import build_radar_service
from umbral.infrastructure.scoring.composition import build_scoring_service

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def scoring_backend(request: pytest.FixtureRequest) -> SessionFactory:
    """Postgres at head for one scoring integration test."""
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


def build_scoring(
    factory: SessionFactory, comparator_enabled: bool = False
) -> ScoringService:
    return build_scoring_service(
        session_factory=factory,
        policy_seed_version="scoring-policy-v1",
        legacy_score_policy_version="scoring-baseline-v1",
        comparison_max_listings=6,
        comparator_enabled=comparator_enabled,
        clock=lambda: _NOW,
    )


def build_radar(factory: SessionFactory, scoring: ScoringService) -> RadarService:
    return build_radar_service(
        session_factory=factory,
        job_runtime=None,
        policy_engine=scoring,
        score_policy_version="scoring-policy-v1",
        clock=lambda: _NOW,
    )


def seed_criteria_observations(factory: SessionFactory) -> list[UUID]:
    """Seed the concept registry and extract all concepts over the fixture listings."""
    from tests.integration.criteria.conftest import (
        build_criteria_service,
        seed_silver_listings,
    )

    from umbral.application.criteria.contracts import RecomputeScope

    listing_ids = seed_silver_listings(factory, count=3)
    criteria = build_criteria_service(factory)
    criteria.seed_registry(correlation_id=uuid4())
    criteria.process_extraction(RecomputeScope("full", None), job_execution_id=uuid4())
    return listing_ids


def seed_run(factory: SessionFactory) -> tuple[Any, Any, Any]:
    """Full run v1 pipeline: listings + observations + profile + criteria -> run."""
    from tests.integration.criteria.conftest import (
        build_criteria_service,
        seed_silver_listings,
    )
    from tests.integration.radar.conftest import seed_user

    from umbral.application.criteria.contracts import RecomputeScope
    from umbral.application.radar.contracts import ProfileVersion, RecommendationRun

    seed_silver_listings(factory, count=3)
    criteria = build_criteria_service(factory)
    criteria.seed_registry(correlation_id=uuid4())
    criteria.process_extraction(RecomputeScope("full", None), job_execution_id=uuid4())
    owner_id = seed_user(factory)
    profile = build_profile(
        owner_id=owner_id,
        zones=("caballito",),
        budget_max=600000.0,
        min_rooms=2,
    )
    from umbral.infrastructure.db.repositories.radar import (
        SqlAlchemyProfileVersionRepository,
        SqlAlchemyRunRepository,
        SqlAlchemySearchProfileRepository,
    )

    profiles = SqlAlchemySearchProfileRepository(factory)
    versions = SqlAlchemyProfileVersionRepository(factory)
    profiles.insert(profile)
    version = ProfileVersion(
        version_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version=1,
        payload={
            "name": profile.name,
            "operation": profile.operation,
            "zones": list(profile.zones),
            "budget_max": profile.budget_max,
            "budget_min": profile.budget_min,
            "min_rooms": profile.min_rooms,
            "surface_min": profile.surface_min,
            "surface_max": profile.surface_max,
            "status": profile.status,
            "unknown_strategy": dict(profile.unknown_strategy),
        },
        created_at=_NOW,
        correlation_id=uuid4(),
    )
    versions.insert(version)
    criteria.record_preference_fact(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        concept_key="balcon",
        value="si",
        weight=0.5,
        polarity="positive",
        confidence=1.0,
        fact_source="harness",
        correlation_id=uuid4(),
    )
    criteria.compile_profile(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        edits=(),
        correlation_id=uuid4(),
    )
    scoring = build_scoring(factory)
    radar = build_radar(factory, scoring)
    runs = SqlAlchemyRunRepository(factory)
    run = RecommendationRun(
        run_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        state="running",
        trigger="created",
        score_policy_version="scoring-policy-v1",
        candidate_count=0,
        published_item_count=0,
        failure_code=None,
        job_execution_id=None,
        created_at=_NOW,
        finished_at=None,
        correlation_id=uuid4(),
        version=1,
    )
    runs.insert(run)
    radar.process_run(
        run_id=run.run_id,
        job_execution_id=uuid4(),
    )
    return radar, profile, runs.get(run.run_id)
