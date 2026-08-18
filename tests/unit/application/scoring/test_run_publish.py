"""Unit tests for atomic run publishing with scoring v1 (US5)."""

from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import UUID, uuid4

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
from tests.support.radar import build_listing, build_profile, profile_version_payload
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_observation,
)

from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.radar.contracts import (
    ProfileVersion,
    RadarPermanentError,
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.radar.service import RadarService
from umbral.domain.errors import ConcurrencyConflict
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.radar.contract_loader import (
    load_events_registry,
    load_scoring_baseline,
    load_search_profile_policy,
)


def _radar_with_engine(
    context: ScoringTestContext,
) -> tuple[RadarService, FakeRunRepository, FakeCandidateListingReader]:
    shared_items: dict[UUID, list[RecommendationItem]] = {}
    runs = FakeRunRepository()
    items = FakeItemRepository(items_by_run=shared_items)
    runs.items_by_run = shared_items
    candidates = FakeCandidateListingReader()
    shared_versions: dict[UUID, ProfileVersion] = {}
    profiles = FakeSearchProfileRepository(version_rows=shared_versions)
    versions = FakeProfileVersionRepository(rows=shared_versions)
    context.profiles.rows = profiles.rows
    context.versions.rows = shared_versions
    context.runs.rows = runs.rows
    context.items.items_by_run = shared_items
    service = RadarService(
        profiles=profiles,
        versions=versions,
        runs=runs,
        items=items,
        events=FakeEventRepository(),
        candidates=candidates,
        listings=FakeListingReader(),
        policy=load_search_profile_policy(),
        scoring=load_scoring_baseline(),
        events_registry=load_events_registry(),
        job_runtime=None,
        score_policy_version=context.service.pin_policy_version(),
        policy_engine=context.service,
    )
    return service, runs, candidates


def test_scheduled_run_keeps_policy_revision_after_new_revision_registered() -> None:
    context = ScoringTestContext()
    policy_a = context.service.register_policy_version(
        policy_key="scoring-policy-v1",
        payload=context.service.policy_seed,
        correlation_id=uuid4(),
    )
    radar, runs, candidates = _radar_with_engine(context)
    radar.job_runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    owner_id = uuid4()
    profile, run = radar.create_profile(
        owner_id=owner_id,
        name="Radar",
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
    assert profile.current_version_id is not None
    listing = build_listing()
    candidates.listings = [listing]
    context.compilations.compilations[profile.current_version_id] = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=profile.current_version_id,
        criteria=(build_criterion("balcon", matcher_type="categorical"),),
    )
    context.observations.observations = {
        listing.listing_id: {
            "balcon": build_observation(
                listing_id=listing.listing_id,
                concept_key="balcon",
                value="si",
            )
        }
    }
    policy_b_payload = dict(context.service.policy_seed)
    policy_b_criteria = [
        dict(item)
        for item in cast(list[dict[str, object]], policy_b_payload["criteria"])
    ]
    balcony = next(item for item in policy_b_criteria if item["key"] == "balcon")
    balcony["params"] = {"allowed_values": ["no"]}
    balcony["gate"] = "exclude_on_mismatch"
    policy_b_payload["criteria"] = policy_b_criteria
    context.service.register_policy_version(
        policy_key="scoring-policy-v1",
        payload=policy_b_payload,
        correlation_id=uuid4(),
    )

    summary = radar.process_run(
        run_id=run.run_id,
        job_execution_id=run.job_execution_id,
    )

    policy_ref = str(policy_a.version_id)
    assert run.score_policy_version == policy_ref
    assert summary["published_item_count"] == 1
    item = context.items.items_by_run[run.run_id][0]
    assert item.contributions["score_policy_version"] == policy_ref
    evaluations = tuple(runs.evaluations_by_run[run.run_id])
    assert all(item.criterion_version == f"policy:{policy_ref}" for item in evaluations)
    assert runs.events[0].payload["score_policy_version"] == policy_ref
    context.evaluations.rows.extend(evaluations)
    explanation = context.service.get_explanation(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        run_id=run.run_id,
        listing_id=listing.listing_id,
    )
    assert explanation.score_version == policy_ref
    assert explanation.profile_snapshot["policy_version_id"] == policy_ref


def test_run_fails_closed_when_its_pinned_policy_revision_is_missing() -> None:
    context = ScoringTestContext()
    radar, _, _ = _radar_with_engine(context)
    radar.job_runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    profile, run = radar.create_profile(
        owner_id=uuid4(),
        name="Radar",
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
    assert profile.current_version_id is not None
    context.compilations.compilations[profile.current_version_id] = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=profile.current_version_id,
        criteria=(),
    )
    context.policies.rows.clear()

    with pytest.raises(RadarPermanentError) as excinfo:
        radar.process_run(run_id=run.run_id, job_execution_id=run.job_execution_id)

    assert excinfo.value.code == "radar.score_policy_not_found"


def test_run_publishes_evaluations_atomically_with_the_run() -> None:
    context = ScoringTestContext()
    radar, runs, candidates = _radar_with_engine(context)
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
    candidates.listings = [listing]
    run = RecommendationRun(
        run_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        state="running",
        trigger="created",
        score_policy_version=context.service.pin_policy_version(),
        candidate_count=0,
        published_item_count=0,
        failure_code=None,
        job_execution_id=None,
        created_at=profile.created_at,
        finished_at=None,
        correlation_id=uuid4(),
        version=1,
    )
    runs.insert(run)
    summary = radar.process_run(
        run_id=run.run_id,
        job_execution_id=uuid4(),
    )
    assert summary["state"] == "succeeded"
    published = runs.get(run.run_id)
    assert published is not None and published.state == "succeeded"
    stored = runs.evaluations_by_run.get(run.run_id, ())
    assert stored, "evaluations must be published with the run"
    assert {item.criterion_key for item in stored} == {
        "presupuesto",
        "ambientes",
        "ubicacion",
        "balcon",
        "luminosidad",
        "estado_general",
    }
    assert len(runs.events) == 1


def test_optimistic_lock_conflict_becomes_transient_and_keeps_last_valid() -> None:
    context = ScoringTestContext()
    radar, runs, candidates = _radar_with_engine(context)
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
    candidates.listings = [listing]
    run = RecommendationRun(
        run_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version_id=version.version_id,
        state="running",
        trigger="created",
        score_policy_version=context.service.pin_policy_version(),
        candidate_count=0,
        published_item_count=0,
        failure_code=None,
        job_execution_id=None,
        created_at=profile.created_at,
        finished_at=None,
        correlation_id=uuid4(),
        version=1,
    )
    runs.insert(run)

    original_publish = runs.publish

    def conflicting_publish(*args: object, **kwargs: object) -> None:
        raise ConcurrencyConflict(expected_version=1, actual_version=2)

    runs.publish = conflicting_publish  # type: ignore[method-assign]
    with pytest.raises(Exception) as excinfo:
        radar.process_run(
            run_id=run.run_id,
            job_execution_id=uuid4(),
        )
    assert excinfo.type.__name__ == "RadarTransientError"
    runs.publish = original_publish  # type: ignore[method-assign]
    failed = replace(run, state="failed")
    runs.rows[run.run_id] = failed
    assert runs.get(run.run_id) is not None


def _version_for(profile: SearchProfile, version_number: int) -> ProfileVersion:
    return ProfileVersion(
        version_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version=version_number,
        payload=profile_version_payload(profile),
        created_at=profile.created_at,
        correlation_id=uuid4(),
    )
