"""Stable paging over frozen matches of one run against real Postgres."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

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


def test_paging_over_run_items_has_no_repeats_or_omissions(radar_backend: Any) -> None:
    factory = radar_backend
    seed_silver_listings(factory, count=6)
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    handler = RecommendationRunHandler(service)

    profile, run = service.create_profile(
        owner_id=user_id,
        name="Radar pagina",
        zones=("palermo",),
        budget_max=1200.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    assert run is not None
    summary = handler.run(_context(str(run.run_id)))
    assert summary["published_item_count"] == 6

    seen: list[object] = []
    after: int | None = None
    while True:
        page = service.get_matches(
            owner_id=user_id,
            profile_id=profile.profile_id,
            run_id=None,
            after_position=after,
            limit=2,
        )
        assert page.run.state == "succeeded"
        seen.extend(item.listing_id for item in page.items)
        if page.next_after_position is None:
            break
        after = page.next_after_position

    assert len(seen) == 6
    assert len(set(seen)) == 6


def test_explicit_run_id_pages_the_same_frozen_set(radar_backend: Any) -> None:
    factory = radar_backend
    seed_silver_listings(factory, count=4)
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    handler = RecommendationRunHandler(service)

    profile, run = service.create_profile(
        owner_id=user_id,
        name="Radar run",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    assert run is not None
    handler.run(_context(str(run.run_id)))
    succeeded = service.runs.latest_succeeded_for_profile(profile.profile_id)
    assert succeeded is not None

    first_page = service.get_matches(
        owner_id=user_id,
        profile_id=profile.profile_id,
        run_id=succeeded.run_id,
        after_position=None,
        limit=2,
    )
    second_page = service.get_matches(
        owner_id=user_id,
        profile_id=profile.profile_id,
        run_id=succeeded.run_id,
        after_position=first_page.next_after_position,
        limit=2,
    )
    assert first_page.run.run_id == succeeded.run_id
    assert len(first_page.items) == 2
    assert len(second_page.items) == 2
    combined = [item.listing_id for item in first_page.items] + [
        item.listing_id for item in second_page.items
    ]
    assert len(set(combined)) == 4
