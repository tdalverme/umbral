"""Shared Postgres backend and Silver seeding for radar integration tests."""

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
from tests.support.radar import build_listing

from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.radar.service import RadarService
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyCandidateListingReader,
    SqlAlchemyEventRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyListingReader,
    SqlAlchemyProfileVersionRepository,
    SqlAlchemyRunRepository,
    SqlAlchemySearchProfileRepository,
)
from umbral.infrastructure.db.repositories.silver import (
    SqlAlchemyCanonicalPropertyRepository,
    SqlAlchemySilverListingRepository,
)
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.radar.contract_loader import (
    load_events_registry,
    load_scoring_baseline,
    load_search_profile_policy,
)

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def radar_backend(request: pytest.FixtureRequest) -> SessionFactory:
    """Postgres at head for one radar integration test."""
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


def seed_user(factory: SessionFactory) -> UUID:
    """Create one active product user and return its id."""
    from umbral.domain.identity.models import ProductUser, RoleAssignment
    from umbral.infrastructure.db.repositories.identity import (
        SqlAlchemyIdentityStore,
    )

    store = SqlAlchemyIdentityStore(
        factory, fingerprint_key=b"test", environment="local"
    )
    user_id = uuid4()
    with store.transaction():
        store.save_user(
            ProductUser(
                id=user_id,
                normalized_email=f"radar-{user_id}@example.invalid",
                status="active",
            )
        )
        store.save_role(
            RoleAssignment(
                id=uuid4(),
                product_user_id=user_id,
                role="user",
                granted_at=_NOW,
            )
        )
    return user_id


def seed_silver_listings(factory: SessionFactory, count: int = 3) -> None:
    """Insert one import run + canonical properties + silver listings."""
    from tests.support.silver import build_run

    from umbral.application.ingestion.contracts import RawListingSnapshot
    from umbral.infrastructure.db.repositories.imports import (
        SqlAlchemyImportRunRepository,
        SqlAlchemyRawSnapshotRepository,
    )

    run_repo = SqlAlchemyImportRunRepository(factory)
    import_run = run_repo.create(
        run_id=uuid4(),
        source=build_run(source_id="fixture").source,
        batch_key="radar-seed",
        file_format="json",
        file_name="radar-seed.json",
        file_sha256="0" * 64,
        file_size_bytes=0,
        raw_storage_key=f"objects/raw/{uuid4()}",
        job_execution_id=None,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
        now=_NOW,
    )
    snapshots = SqlAlchemyRawSnapshotRepository(factory)
    canonicals = SqlAlchemyCanonicalPropertyRepository(factory)
    listings = SqlAlchemySilverListingRepository(factory)
    for index in range(count):
        canonical = canonicals.create(
            canonical_property_id=uuid4(),
            first_seen_at=_NOW,
            correlation_id=uuid4(),
            actor_kind="system",
            actor_id=None,
        )
        snapshot_id = uuid4()
        snapshots.insert(
            RawListingSnapshot(
                snapshot_id=snapshot_id,
                run_id=import_run.run_id,
                source=import_run.source,
                external_id=f"seed-{index}",
                payload={},
                content_sha256="0" * 64,
                content_type="application/json",
                size_bytes=0,
                published_at=_NOW,
                captured_at=_NOW,
            )
        )
        total_cost = 600.0 + index * 100.0
        listing = build_listing(
            total_cost=total_cost,
            neighborhood="palermo",
            rooms=2 + (index % 2),
            surface_m2=45.0 + index * 5.0,
            geo_precision=("exact" if index % 3 == 0 else "neighborhood"),
        )
        from dataclasses import replace

        listing = replace(
            listing,
            canonical_property_id=canonical.canonical_property_id,
            run_id=import_run.run_id,
            snapshot_id=snapshot_id,
        )
        listings.insert(listing)


def build_radar_service(
    factory: SessionFactory,
    *,
    job_runtime: InMemoryJobRuntime | None = None,
) -> RadarService:
    runtime = job_runtime or InMemoryJobRuntime(queue=RecordingJobQueue())
    return RadarService(
        profiles=SqlAlchemySearchProfileRepository(factory),
        versions=SqlAlchemyProfileVersionRepository(factory),
        runs=SqlAlchemyRunRepository(factory),
        items=SqlAlchemyItemRepository(factory),
        events=SqlAlchemyEventRepository(factory),
        candidates=SqlAlchemyCandidateListingReader(factory),
        listings=SqlAlchemyListingReader(factory),
        policy=load_search_profile_policy(),
        scoring=load_scoring_baseline(),
        events_registry=load_events_registry(),
        job_runtime=runtime,
        run_job_type="recommendation.run",
        score_policy_version="scoring-baseline-v1",
    )
