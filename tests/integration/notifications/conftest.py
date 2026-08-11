# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Shared Postgres backend and FK seeding for notifications tests (H5)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from tests.support.containers import ServiceConnection

from umbral.infrastructure.db.models.radar import (
    RecommendationItem,
    RecommendationRun,
    SearchProfileVersion,
)
from umbral.infrastructure.db.models.silver import SilverListing
from umbral.infrastructure.notifications.repositories import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyPreferenceRepository,
)

_NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def notification_backend(request: pytest.FixtureRequest) -> tuple[object, str]:
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory, connection.url


@pytest.fixture
def notification_repos(notification_backend):
    factory, _url = notification_backend
    return {
        "factory": factory,
        "preferences": SqlAlchemyPreferenceRepository(factory),
        "decisions": SqlAlchemyDecisionRepository(factory),
    }


@pytest.fixture
def notification_seed(notification_backend):
    """Seed user + profile + silver listing + published run/item for FKs."""
    factory, _url = notification_backend
    from tests.integration.chat.conftest import seed_profile
    from tests.integration.radar.conftest import seed_silver_listings, seed_user

    user = seed_user(factory)
    profile = seed_profile(factory, cast(UUID, user))
    seed_silver_listings(factory, count=1)
    with factory() as session:
        listing_id = session.execute(
            select(SilverListing.id).limit(1)
        ).scalar_one()
        profile_version_id = session.execute(
            select(SearchProfileVersion.id)
            .where(SearchProfileVersion.profile_id == profile.profile_id)
            .order_by(SearchProfileVersion.profile_version.desc())
            .limit(1)
        ).scalar_one()
        run_id = uuid4()
        session.add(
            RecommendationRun(
                id=run_id,
                profile_id=profile.profile_id,
                profile_version_id=profile_version_id,
                state="succeeded",
                trigger="created",
                score_policy_version="scoring-policy-v1",
                candidate_count=1,
                published_item_count=1,
                finished_at=_NOW,
                created_at=_NOW,
                updated_at=_NOW,
                source="test",
                correlation_id=uuid4(),
            )
        )
        session.commit()
        item_id = uuid4()
        session.add(
            RecommendationItem(
                id=item_id,
                run_id=run_id,
                listing_id=listing_id,
                score=0.9,
                position=1,
                contributions={},
                created_at=_NOW,
                updated_at=_NOW,
                source="test",
                correlation_id=uuid4(),
            )
        )
        session.commit()
    return {
        "user_id": user,
        "search_profile_id": profile.profile_id,
        "recommendation_item_id": item_id,
        "factory": factory,
    }
