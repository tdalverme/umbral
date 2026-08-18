"""PostgreSQL preference adapter fixtures."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from tests.fakes.preferences import FakeConceptReader
from tests.integration.radar.conftest import seed_user
from tests.support.containers import ServiceConnection
from tests.support.radar import build_profile

from umbral.application.preferences.contracts import (
    PreferenceConcept,
    PreferencePolicySpec,
)
from umbral.application.preferences.service import PreferenceService
from umbral.application.radar.contracts import ProfileVersion
from umbral.infrastructure.db.models.criteria import Concept, ExtractionVersion
from umbral.infrastructure.db.repositories.preferences import (
    SqlAlchemyBindingRepository,
    SqlAlchemyExpressionRepository,
)
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyProfileVersionRepository,
    SqlAlchemySearchProfileRepository,
)

SessionFactory = Callable[[], Session]
_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class PreferenceStack:
    factory: SessionFactory
    service: PreferenceService
    expressions: SqlAlchemyExpressionRepository
    bindings: SqlAlchemyBindingRepository
    profile_id: UUID
    profile_version_id: UUID
    embedding_version_id: UUID


@pytest.fixture
def preference_stack(
    request: pytest.FixtureRequest,
) -> PreferenceStack:
    external_url = os.getenv("UMBRAL_TEST_POSTGRES_URL")
    connection = (
        ServiceConnection(
            service="postgres",
            host="127.0.0.1",
            port=5432,
            url=external_url,
            container=None,
        )
        if external_url
        else request.getfixturevalue("postgres_container")
    )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)
    request.addfinalizer(engine.dispose)

    owner_id = seed_user(factory)
    profile = build_profile(owner_id=owner_id, name="Preferencias")
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
    embedding_version_id = uuid4()
    with factory() as session:
        if session.scalar(select(Concept).where(Concept.key == "balcon")) is None:
            session.add(
                Concept(
                    id=uuid4(),
                    created_at=_NOW,
                    updated_at=_NOW,
                    actor_kind="service",
                    actor_id=None,
                    source="preference-test",
                    correlation_id=uuid4(),
                    key="balcon",
                    name="Balcón",
                    aliases=[],
                    matcher_type="categorical",
                    params_schema={},
                    defaults={},
                    compute_policy={"computable": True},
                    current_version_id=None,
                )
            )
        session.add(
            ExtractionVersion(
                    id=embedding_version_id,
                    created_at=_NOW,
                    updated_at=_NOW,
                    actor_kind="service",
                    actor_id=None,
                    source="preference-test",
                    correlation_id=uuid4(),
                    kind="embedding",
                    key=f"preference-query-{profile.profile_id}",
                    artifact_version="embedding-v1",
                    payload={},
                )
        )
        session.commit()

    expressions = SqlAlchemyExpressionRepository(factory)
    bindings = SqlAlchemyBindingRepository(factory)
    service = PreferenceService(
        expressions=expressions,
        bindings=bindings,
        mutations=expressions,
        concepts=FakeConceptReader(
            {
                "balcon": PreferenceConcept(
                    key="balcon", matcher_type="categorical", computable=True
                )
            }
        ),
        policy=PreferencePolicySpec.v1(),
        clock=lambda: _NOW,
    )
    return PreferenceStack(
        factory=factory,
        service=service,
        expressions=expressions,
        bindings=bindings,
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        embedding_version_id=embedding_version_id,
    )
