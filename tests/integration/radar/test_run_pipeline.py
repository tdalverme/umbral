"""Recommendation run pipeline against real Postgres: publish, determinism, recovery."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from tests.integration.radar.conftest import (
    build_radar_service,
    seed_silver_listings,
    seed_user,
)

from umbral.application.radar.contracts import RadarValidationError
from umbral.workers.radar import RecommendationRunHandler


def _create_and_run(
    service: Any, handler: Any, *, owner: Any, name: str, min_rooms: int = 1
) -> tuple[Any, Any, dict[str, Any]]:
    profile, run = service.create_profile(
        owner_id=owner,
        name=name,
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=min_rooms,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    summary = handler.run(
        _context(f"{profile.profile_id}:{profile.current_version_id}")
    )
    return profile, run, summary


def _context(logical_target: str) -> Any:
    from umbral.application.jobs.contracts import JobContext

    return JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target=logical_target,
    )


def test_run_pipeline_publishes_atomically(radar_backend: Any) -> None:
    factory = radar_backend
    seed_silver_listings(factory, count=3)
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    handler = RecommendationRunHandler(service)
    profile, _, summary = _create_and_run(
        service, handler, owner=user_id, name="Radar A"
    )

    assert summary["state"] == "succeeded"
    assert summary["candidate_count"] == 3
    assert summary["published_item_count"] == 3

    page = service.get_matches(
        owner_id=user_id,
        profile_id=profile.profile_id,
        run_id=None,
        after_position=None,
        limit=100,
    )
    assert page.run.state == "succeeded"
    assert len(page.items) == 3
    positions = [item.position for item in page.items]
    assert positions == sorted(positions)
    assert page.items[0].contributions["score_policy_version"] == "scoring-baseline-v1"

    events = _events_of(factory)
    assert "radar.created.v1" in events
    assert "recommendation.run_published.v1" in events


def test_identical_profiles_produce_identical_orders(radar_backend: Any) -> None:
    factory = radar_backend
    seed_silver_listings(factory, count=3)
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    handler = RecommendationRunHandler(service)

    first_profile, _, first_summary = _create_and_run(
        service, handler, owner=user_id, name="A", min_rooms=1
    )
    second_profile, _, second_summary = _create_and_run(
        service, handler, owner=user_id, name="B", min_rooms=1
    )
    assert first_summary["candidate_count"] == second_summary["candidate_count"]

    first_page = service.get_matches(
        owner_id=user_id,
        profile_id=first_profile.profile_id,
        run_id=None,
        after_position=None,
        limit=100,
    )
    second_page = service.get_matches(
        owner_id=user_id,
        profile_id=second_profile.profile_id,
        run_id=None,
        after_position=None,
        limit=100,
    )
    assert [item.listing_id for item in first_page.items] == [
        item.listing_id for item in second_page.items
    ]
    assert [item.score for item in first_page.items] == [
        item.score for item in second_page.items
    ]


def test_failed_run_keeps_last_valid_run_visible(radar_backend: Any) -> None:
    factory = radar_backend
    seed_silver_listings(factory, count=3)
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    handler = RecommendationRunHandler(service)
    profile, _, summary = _create_and_run(
        service, handler, owner=user_id, name="Radar F"
    )
    assert summary["state"] == "succeeded"

    first_valid = service.runs.latest_succeeded_for_profile(profile.profile_id)
    assert first_valid is not None

    updated, _ = service.update_profile(
        owner_id=user_id,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"name": "Radar F editado"},
        correlation_id=uuid4(),
    )
    latest_version = service.versions.latest_for_profile(profile.profile_id)
    assert latest_version is not None
    failing_run = service.runs.get_for_version(
        profile.profile_id, latest_version.version_id
    )
    assert failing_run is not None
    assert failing_run.state == "pending"
    service.runs.fail(failing_run, "radar.induced_failure")

    page = service.get_matches(
        owner_id=user_id,
        profile_id=profile.profile_id,
        run_id=None,
        after_position=None,
        limit=100,
    )
    assert page.run.run_id == first_valid.run_id
    assert page.run.state == "succeeded"
    assert len(page.items) == 3
    assert updated.version == profile.version + 1


def test_invalid_profile_is_rejected_without_side_effects(radar_backend: Any) -> None:
    import pytest

    factory = radar_backend
    seed_silver_listings(factory, count=1)
    user_id = seed_user(factory)
    service = build_radar_service(factory)

    with pytest.raises(RadarValidationError):
        service.create_profile(
            owner_id=user_id,
            name="Invalido",
            zones=(),
            budget_max=1000.0,
            budget_min=None,
            min_rooms=0,
            surface_min=None,
            surface_max=None,
            unknown_strategy=None,
            correlation_id=uuid4(),
        )


def _events_of(factory: Any) -> list[str]:
    from sqlalchemy import select

    from umbral.infrastructure.db.models.radar import ProductEventRow

    with factory() as session:
        return list(session.scalars(select(ProductEventRow.event_type)))
