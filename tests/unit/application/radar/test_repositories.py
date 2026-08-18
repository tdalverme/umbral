"""In-memory radar repository guard behaviors (uniqueness, ordering, locking)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Barrier
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from tests.fakes.radar import (
    FakeProfileVersionRepository,
    FakeRunRepository,
    FakeSearchProfileRepository,
)
from tests.support.radar import build_profile

from umbral.application.events.contracts import ProductEvent
from umbral.application.radar.contracts import (
    ProfileVersion,
    RecommendationItem,
    RecommendationRun,
)
from umbral.domain.errors import ConcurrencyConflict
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyCandidateListingReader,
    SqlAlchemySearchProfileRepository,
)

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _version(profile_id: UUID, number: int) -> ProfileVersion:
    return ProfileVersion(
        version_id=uuid4(),
        profile_id=profile_id,
        profile_version=number,
        payload={},
        created_at=NOW,
        correlation_id=uuid4(),
    )


def test_profile_insert_get_and_owner_listing() -> None:
    repository = FakeSearchProfileRepository()
    owner = uuid4()
    first = build_profile(owner_id=owner, name="A", created_at=NOW)
    second = build_profile(owner_id=owner, name="B", created_at=NOW)
    third = build_profile(owner_id=uuid4(), name="Otro", created_at=NOW)
    for profile in (first, second, third):
        repository.insert(profile)
    assert repository.get(first.profile_id) == first
    listed = repository.list_by_owner(owner, None)
    assert {profile.name for profile in listed} == {"A", "B"}
    paused = repository.list_by_owner(owner, "paused")
    assert paused == ()


def test_save_guards_the_optimistic_version() -> None:
    repository = FakeSearchProfileRepository()
    profile = build_profile()
    repository.insert(profile)
    with pytest.raises(ConcurrencyConflict):
        repository.save(build_profile(profile_id=profile.profile_id, version=99))
    repository.save(build_profile(profile_id=profile.profile_id, version=1))
    assert repository.rows[profile.profile_id].version == 2


def test_sql_status_save_translates_a_commit_time_stale_write() -> None:
    profile = build_profile()

    class StaleCommitSession:
        rolled_back = False
        model = SimpleNamespace(version=profile.version)

        def __enter__(self) -> "StaleCommitSession":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def get(self, model_type: object, profile_id: UUID) -> object:
            del model_type, profile_id
            if self.rolled_back:
                return SimpleNamespace(version=profile.version + 1)
            return self.model

        def commit(self) -> None:
            raise StaleDataError("concurrent update")

        def rollback(self) -> None:
            self.rolled_back = True

    session = StaleCommitSession()
    repository = SqlAlchemySearchProfileRepository(lambda: cast(Session, session))

    with pytest.raises(ConcurrencyConflict) as excinfo:
        repository.save(replace(profile, status="paused"))

    assert session.rolled_back
    assert excinfo.value.expected_version == profile.version
    assert excinfo.value.actual_version == profile.version + 1


def test_version_repository_returns_latest_by_number() -> None:
    repository = FakeProfileVersionRepository()
    profile_id = uuid4()
    first = _version(profile_id, 1)
    second = _version(profile_id, 2)
    repository.insert(first)
    repository.insert(second)
    assert repository.latest_for_profile(profile_id) == second
    assert repository.get(first.version_id) == first


def test_open_profile_candidate_query_omits_unset_predicates() -> None:
    class EmptyRows:
        def all(self) -> list[object]:
            return []

    class RecordingSession:
        statement: object | None = None

        def __enter__(self) -> "RecordingSession":
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def execute(self, statement: object) -> EmptyRows:
            self.statement = statement
            return EmptyRows()

    session = RecordingSession()
    reader = SqlAlchemyCandidateListingReader(lambda: cast(Session, session))

    assert reader.list_candidates(
        build_profile(zones=(), budget_max=None, min_rooms=None),
        supported_neighborhoods=("palermo", "recoleta"),
        supported_property_types=("apartment", "house", "room", "studio"),
    ) == ()
    sql = str(session.statement)
    assert "total_cost <=" not in sql
    assert "property_type IN" in sql
    assert "lower(silver_listings.neighborhood)" in sql
    assert "silver_listings.rooms >=" not in sql


def test_run_repository_publishes_items_and_event_atomically() -> None:
    repository = FakeRunRepository()
    profile_id = uuid4()
    version_id = uuid4()
    run = build_run(profile_id, version_id)
    repository.insert(run)
    items = (
        RecommendationItem(
            item_id=uuid4(),
            run_id=run.run_id,
            listing_id=uuid4(),
            score=0.5,
            position=0,
            contributions={},
        ),
    )
    event = ProductEvent(
        event_id=uuid4(),
        event_type="recommendation.run_published.v1",
        event_version=1,
        actor_id=None,
        occurred_at=NOW,
        correlation_id=uuid4(),
        payload={},
    )
    repository.publish(run, items, event)
    published = repository.get(run.run_id)
    assert published is not None
    assert published.state == "succeeded"
    assert published.published_item_count == 1
    assert len(repository.events) == 1
    assert repository.items_by_run[run.run_id] == list(items)


def test_run_repository_fail_records_code() -> None:
    repository = FakeRunRepository()
    run = build_run(uuid4(), uuid4())
    repository.insert(run)
    repository.fail(run, "radar.test_failure")
    failed = repository.get(run.run_id)
    assert failed is not None
    assert failed.state == "failed"
    assert failed.failure_code == "radar.test_failure"


def test_concurrent_run_reservations_return_one_durable_run() -> None:
    repository = FakeRunRepository()
    profile_id = uuid4()
    version_id = uuid4()
    first = build_run(profile_id, version_id)
    second = replace(first, run_id=uuid4())
    barrier = Barrier(2)

    def reserve(run: RecommendationRun) -> RecommendationRun:
        barrier.wait()
        return repository.reserve(run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(reserve, (first, second)))

    assert results[0].run_id == results[1].run_id
    assert len(repository.rows) == 1


def build_run(profile_id: UUID, version_id: UUID) -> RecommendationRun:
    return RecommendationRun(
        run_id=uuid4(),
        profile_id=profile_id,
        profile_version_id=version_id,
        state="pending",
        trigger="created",
        score_policy_version="scoring-baseline-v1",
        candidate_count=0,
        published_item_count=0,
        failure_code=None,
        job_execution_id=None,
        created_at=NOW,
        finished_at=None,
        correlation_id=uuid4(),
    )
