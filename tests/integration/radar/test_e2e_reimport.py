"""End-to-end re-import idempotency: no duplicate runs or matches."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from tests.integration.radar.conftest import (
    build_radar_service,
    seed_silver_listings,
    seed_user,
)

from umbral.workers.radar import RecommendationRunHandler


def _context(logical_target: str) -> Any:
    from umbral.application.jobs.contracts import JobContext

    return JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target=logical_target,
    )


def test_reimporting_creates_no_duplicate_runs_or_matches(radar_backend: Any) -> None:
    factory = radar_backend
    seed_silver_listings(factory, count=3)
    user_id = cast(UUID, seed_user(factory))
    service = build_radar_service(factory)
    handler = RecommendationRunHandler(service)

    profile, _ = service.create_profile(
        owner_id=user_id,
        name="Radar E2E",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    target = f"{profile.profile_id}:{profile.current_version_id}"
    first = handler.run(_context(target))
    assert first["published_item_count"] == 3

    replay = handler.run(_context(target))
    assert replay["run_id"] == first["run_id"]
    assert replay["published_item_count"] == 3

    runs = (
        [run for run in service.runs.rows.values()]
        if hasattr(service.runs, "rows")
        else _all_runs(factory)
    )
    assert len(runs) == 1

    page = service.get_matches(
        owner_id=user_id,
        profile_id=profile.profile_id,
        run_id=None,
        after_position=None,
        limit=100,
    )
    assert page.run.state == "succeeded"
    assert len(page.items) == 3


def _all_runs(factory: Any) -> list[Any]:
    from sqlalchemy import select

    from umbral.infrastructure.db.models.radar import RecommendationRun as RunModel

    with factory() as session:
        return list(session.scalars(select(RunModel)))
