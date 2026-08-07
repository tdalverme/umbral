"""Unit tests for atomic run publishing with scoring v1 (US5)."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from tests.fakes.radar import (
    FakeCandidateListingReader,
    FakeEventRepository,
    FakeItemRepository,
    FakeListingReader,
    FakeProfileVersionRepository,
    FakeRunRepository,
    FakeSearchProfileRepository,
)
from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)

from umbral.application.radar.contracts import RecommendationRun
from umbral.application.radar.service import RadarService
from umbral.domain.errors import ConcurrencyConflict
from umbral.infrastructure.radar.contract_loader import (
    load_events_registry,
    load_scoring_baseline,
    load_search_profile_policy,
)


def _radar_with_engine(context: ScoringTestContext) -> RadarService:
    shared_items: dict = {}
    runs = FakeRunRepository()
    items = FakeItemRepository(items_by_run=shared_items)
    runs.items_by_run = shared_items
    service = RadarService(
        profiles=FakeSearchProfileRepository(),
        versions=FakeProfileVersionRepository(),
        runs=runs,
        items=items,
        events=FakeEventRepository(),
        candidates=FakeCandidateListingReader(),
        listings=FakeListingReader(),
        policy=load_search_profile_policy(),
        scoring=load_scoring_baseline(),
        events_registry=load_events_registry(),
        job_runtime=None,
        score_policy_version="scoring-policy-v1",
        policy_engine=context.service,
    )
    return service


def test_run_publishes_evaluations_atomically_with_the_run() -> None:
    context = ScoringTestContext()
    radar = _radar_with_engine(context)
    profile = build_profile()
    listing = build_listing()
    radar.profiles.insert(profile)
    radar.versions.insert(_version_for(profile, version_number=1))
    version = radar.versions.latest_for_profile(profile.profile_id)
    assert version is not None
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        criteria=(build_criterion("balcon", matcher_type="categorical"),),
    )
    context.compilations.compilations[version.version_id] = compilation
    context.observations.observations = {
        listing.listing_id: {
            "balcon": build_observation(
                listing_id=listing.listing_id, concept_key="balcon", value="si"
            )
        }
    }
    radar.candidates.listings = (listing,)
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
        created_at=profile.created_at,
        finished_at=None,
        correlation_id=uuid4(),
        version=1,
    )
    radar.runs.insert(run)
    summary = radar.process_run(
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        job_execution_id=uuid4(),
    )
    assert summary["state"] == "succeeded"
    published = radar.runs.get(run.run_id)
    assert published is not None and published.state == "succeeded"
    stored = radar.runs.evaluations_by_run.get(run.run_id, ())
    assert stored, "evaluations must be published with the run"
    assert {item.criterion_key for item in stored} == {
        "presupuesto",
        "ambientes",
        "superficie",
        "ubicacion",
        "balcon",
        "luminosidad",
        "estado_general",
    }
    assert len(radar.runs.events) == 1


def test_optimistic_lock_conflict_becomes_transient_and_keeps_last_valid() -> None:
    context = ScoringTestContext()
    radar = _radar_with_engine(context)
    profile = build_profile()
    listing = build_listing()
    radar.profiles.insert(profile)
    version = _version_for(profile, version_number=1)
    radar.versions.insert(version)
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        criteria=(build_criterion("balcon", matcher_type="categorical"),),
    )
    context.compilations.compilations[version.version_id] = compilation
    context.observations.observations = {
        listing.listing_id: {
            "balcon": build_observation(
                listing_id=listing.listing_id, concept_key="balcon", value="si"
            )
        }
    }
    radar.candidates.listings = (listing,)
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
        created_at=profile.created_at,
        finished_at=None,
        correlation_id=uuid4(),
        version=1,
    )
    radar.runs.insert(run)

    original_publish = radar.runs.publish

    def conflicting_publish(*args: object, **kwargs: object) -> None:
        raise ConcurrencyConflict(expected_version=1, actual_version=2)

    radar.runs.publish = conflicting_publish  # type: ignore[method-assign]
    with pytest.raises(Exception) as excinfo:
        radar.process_run(
            profile_id=profile.profile_id,
            profile_version_id=version.version_id,
            job_execution_id=uuid4(),
        )
    assert excinfo.type.__name__ == "RadarTransientError"
    radar.runs.publish = original_publish
    failed = replace(run, state="failed")
    radar.runs.rows[run.run_id] = failed
    assert radar.runs.get(run.run_id) is not None


def _version_for(profile: object, version_number: int) -> object:
    from umbral.application.radar.contracts import ProfileVersion

    return ProfileVersion(
        version_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version=version_number,
        payload={},
        created_at=profile.created_at,
        correlation_id=uuid4(),
    )
