"""RecommendationRunHandler and run processing behavior."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.support.radar import RadarTestContext, build_listing

from umbral.application.jobs.contracts import (
    JobContext,
    PermanentJobError,
)
from umbral.application.radar.contracts import RadarNotAccessible, RecommendationRun
from umbral.application.silver.contracts import NormalizedListing
from umbral.workers.radar import RecommendationRunHandler


def _ctx_with_candidates(*listings: NormalizedListing) -> RadarTestContext:
    ctx = RadarTestContext()
    ctx.candidates.listings = list(listings)
    return ctx


def _run_for(ctx: RadarTestContext, run: RecommendationRun) -> RecommendationRun | None:
    return ctx.runs.get(run.run_id)


def test_handler_processes_a_run_atomically() -> None:
    ctx = _ctx_with_candidates(
        build_listing(total_cost=700.0, rooms=2, geo_precision="neighborhood"),
        build_listing(total_cost=500.0, rooms=3, geo_precision="exact"),
        build_listing(total_cost=2000.0, rooms=1, geo_precision="block"),
    )
    profile, run = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=2,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    handler = RecommendationRunHandler(ctx.service)
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target=f"{profile.profile_id}:{profile.current_version_id}",
    )
    summary = handler.run(context)

    assert summary["state"] == "succeeded"
    assert summary["candidate_count"] == 2
    assert summary["published_item_count"] == 2
    assert run is not None
    persisted = _run_for(ctx, run)
    assert persisted is not None
    assert persisted.state == "succeeded"
    items = ctx.items.list_for_run(persisted.run_id, None, 100)
    assert len(items) == 2
    assert items[0].position == 0
    assert items[0].score > items[1].score
    assert items[0].contributions["score_policy_version"] == "scoring-baseline-v1"
    published_events = [
        event
        for event in ctx.runs.events
        if event.event_type == "recommendation.run_published.v1"
    ]
    assert len(published_events) == 1
    assert published_events[0].payload["candidate_count"] == 2


def test_handler_processes_an_open_partial_profile() -> None:
    ctx = _ctx_with_candidates(build_listing())
    profile, run = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Nueva búsqueda",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    handler = RecommendationRunHandler(ctx.service)
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target=f"{profile.profile_id}:{profile.current_version_id}",
    )

    summary = handler.run(context)

    assert summary["candidate_count"] == 1
    assert run is not None
    items = ctx.items.list_for_run(run.run_id, None, 100)
    assert items[0].contributions["budget"] == 0.0
    assert items[0].contributions["rooms"] == 0.0


def test_hard_filters_exclude_unknown_price_and_out_of_zones() -> None:
    ctx = _ctx_with_candidates(
        build_listing(total_cost=700.0),
        build_listing(neighborhood="recoleta"),
        build_listing(total_cost=1500.0),
    )
    profile, _ = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=0,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    handler = RecommendationRunHandler(ctx.service)
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target=f"{profile.profile_id}:{profile.current_version_id}",
    )
    summary = handler.run(context)
    assert summary["candidate_count"] == 1


def test_terminal_replay_returns_the_existing_result() -> None:
    ctx = _ctx_with_candidates(build_listing(total_cost=700.0))
    profile, run = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=0,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    handler = RecommendationRunHandler(ctx.service)
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target=f"{profile.profile_id}:{profile.current_version_id}",
    )
    first = handler.run(context)
    second = handler.run(context)
    assert first["run_id"] == second["run_id"]
    assert len(ctx.runs.events) == 1


def test_invalid_target_is_a_permanent_failure() -> None:
    ctx = RadarTestContext()
    handler = RecommendationRunHandler(ctx.service)
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target="no-colon-here",
    )
    with pytest.raises(PermanentJobError):
        handler.run(context)


def test_matches_page_of_a_profile_requires_ownership() -> None:
    ctx = RadarTestContext()
    profile, _ = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=0,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    with pytest.raises(RadarNotAccessible):
        ctx.service.get_matches(
            owner_id=uuid4(),
            profile_id=profile.profile_id,
            run_id=None,
            after_position=None,
            limit=25,
        )
