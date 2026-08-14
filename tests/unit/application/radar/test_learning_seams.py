"""RadarService learning seams: bump_profile_version and submit_run (H3.3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from tests.support.radar import RadarTestContext, build_profile

from umbral.application.jobs.contracts import JobSnapshot, SubmitJob
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.radar.contracts import (
    RadarNotAccessible,
    RadarStateError,
    RecommendationRun,
)
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


class _FailOnceRuntime(InMemoryJobRuntime):
    def __init__(self) -> None:
        super().__init__(queue=RecordingJobQueue())
        self.submit_attempts = 0

    def submit(self, command: SubmitJob) -> JobSnapshot:
        self.submit_attempts += 1
        if self.submit_attempts == 1:
            raise RuntimeError("enqueue unavailable")
        return super().submit(command)


class _ControllableRuntime(InMemoryJobRuntime):
    def __init__(self) -> None:
        super().__init__(queue=RecordingJobQueue())
        self.fail_next_submit = False

    def submit(self, command: SubmitJob) -> JobSnapshot:
        if self.fail_next_submit:
            self.fail_next_submit = False
            raise RuntimeError("enqueue unavailable")
        return super().submit(command)


def test_bump_profile_version_snapshots_without_submitting() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    bumped, new_version = ctx.service.bump_profile_version(
        owner_id=owner,
        profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    assert bumped.version == profile.version + 1
    assert new_version.profile_version == 1
    assert new_version.profile_id == profile.profile_id
    assert ctx.runs.rows == {}


def test_version_profile_persists_one_snapshot_without_scheduling() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)

    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"name": "Radar conversacional", "budget_max": None},
        correlation_id=uuid4(),
    )

    assert updated.name == "Radar conversacional"
    assert updated.budget_max is None
    assert version.payload["budget_max"] is None
    assert ctx.runs.rows == {}


def test_schedule_version_run_submits_the_version_once() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )

    first = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )
    second = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )

    assert first is not None
    assert second == first
    assert len(ctx.runs.rows) == 1


def test_schedule_retry_completes_a_durable_reservation_after_enqueue_failure() -> None:
    runtime = _FailOnceRuntime()
    ctx = RadarTestContext(job_runtime=runtime, default_runtime=False)
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )

    with pytest.raises(RuntimeError, match="enqueue unavailable"):
        ctx.service.schedule_version_run(
            profile=updated, version=version, trigger="edited"
        )

    assert len(ctx.runs.rows) == 1
    reserved = next(iter(ctx.runs.rows.values()))
    assert reserved.job_execution_id is None

    retried = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )
    assert retried is not None
    assert retried.run_id == reserved.run_id
    assert retried.job_execution_id is not None


def test_schedule_retry_binds_the_same_job_after_bind_failure() -> None:
    runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    ctx = RadarTestContext(job_runtime=runtime, default_runtime=False)
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )
    ctx.runs.fail_next_bind = True

    with pytest.raises(RuntimeError, match="bind unavailable"):
        ctx.service.schedule_version_run(
            profile=updated, version=version, trigger="edited"
        )

    reserved = next(iter(ctx.runs.rows.values()))
    assert reserved.job_execution_id is None
    assert len(runtime.submissions) == 1

    retried = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )
    assert retried is not None
    assert retried.run_id == reserved.run_id
    assert retried.job_execution_id == runtime.submissions[0].execution_id
    assert len(runtime.submissions) == 1


def test_create_returns_bound_reservation_when_bind_ack_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = RadarTestContext()
    bind_job = ctx.runs.bind_job

    def bind_then_raise(run_id: UUID, execution_id: UUID) -> RecommendationRun:
        bind_job(run_id, execution_id)
        raise RuntimeError("bind acknowledgement lost")

    monkeypatch.setattr(ctx.runs, "bind_job", bind_then_raise)

    profile, recovered = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar ambiguo",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )

    assert recovered is not None
    assert recovered.job_execution_id is not None
    assert recovered.profile_id == profile.profile_id


def test_create_succeeds_when_reservation_and_recovery_store_are_unavailable() -> None:
    ctx = RadarTestContext()
    ctx.runs.fail_next_reserve = True
    ctx.runs.fail_next_get_reserved = True

    profile, scheduled = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar diferido",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )

    assert scheduled is None
    assert profile.current_version_id is not None
    version = ctx.versions.get(profile.current_version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=profile, version=version, trigger="created"
    )
    assert retried is not None
    assert retried.job_execution_id is not None


def test_update_succeeds_when_reservation_fails_and_can_be_scheduled_later() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile, _ = ctx.service.create_profile(
        owner_id=owner,
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
    reserve = ctx.runs.reserve
    failed = False

    def fail_once(run: RecommendationRun) -> RecommendationRun:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("reservation unavailable")
        return reserve(run)

    ctx.runs.reserve = fail_once  # type: ignore[method-assign]

    updated, scheduled = ctx.service.update_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"name": "Radar durable"},
        correlation_id=uuid4(),
    )

    assert updated.name == "Radar durable"
    assert scheduled is None
    assert updated.current_version_id is not None
    assert ctx.runs.get_reserved(
        updated.profile_id, updated.current_version_id, "edited"
    ) is None
    version = ctx.versions.get(updated.current_version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )
    assert retried is not None
    assert retried.job_execution_id is not None


def test_update_succeeds_when_reservation_and_recovery_store_are_unavailable() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile, _ = ctx.service.create_profile(
        owner_id=owner,
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
    ctx.runs.fail_next_reserve = True
    ctx.runs.fail_next_get_reserved = True

    updated, scheduled = ctx.service.update_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"name": "Radar durable"},
        correlation_id=uuid4(),
    )

    assert scheduled is None
    assert updated.current_version_id is not None
    version = ctx.versions.get(updated.current_version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )
    assert retried is not None
    assert retried.job_execution_id is not None


def test_schedule_rejects_a_version_owned_by_another_profile() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )

    with pytest.raises(RadarStateError, match="does not belong"):
        ctx.service.schedule_version_run(
            profile=updated,
            version=replace(version, profile_id=uuid4()),
            trigger="edited",
        )

    assert ctx.runs.rows == {}


def test_submit_run_rejects_a_version_owned_by_another_profile() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )

    with pytest.raises(RadarStateError, match="does not belong"):
        ctx.service.submit_run(
            updated,
            replace(version, profile_id=uuid4()),
            trigger="edited",
        )

    assert ctx.runs.rows == {}


def test_create_returns_reserved_run_when_enqueue_is_deferred() -> None:
    runtime = _FailOnceRuntime()
    ctx = RadarTestContext(job_runtime=runtime, default_runtime=False)

    profile, reserved = ctx.service.create_profile(
        owner_id=uuid4(),
        name="Radar diferido",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )

    assert reserved is not None
    assert reserved.job_execution_id is None
    version_id = profile.current_version_id
    assert version_id is not None
    version = ctx.versions.get(version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=profile, version=version, trigger="created"
    )
    assert retried is not None
    assert retried.run_id == reserved.run_id
    assert retried.job_execution_id is not None


def test_update_returns_reserved_run_when_enqueue_is_deferred() -> None:
    runtime = _ControllableRuntime()
    ctx = RadarTestContext(job_runtime=runtime, default_runtime=False)
    owner = uuid4()
    profile, _ = ctx.service.create_profile(
        owner_id=owner,
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
    runtime.fail_next_submit = True

    updated, reserved = ctx.service.update_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"name": "Radar actualizado"},
        correlation_id=uuid4(),
    )

    assert reserved is not None
    assert reserved.job_execution_id is None
    version_id = updated.current_version_id
    assert version_id is not None
    version = ctx.versions.get(version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=updated, version=version, trigger="edited"
    )
    assert retried is not None
    assert retried.run_id == reserved.run_id
    assert retried.job_execution_id is not None
    assert retried.job_execution_id == runtime.submissions[1].execution_id
    assert len(runtime.submissions) == 2


def test_resume_returns_reserved_run_when_enqueue_is_deferred() -> None:
    runtime = _ControllableRuntime()
    ctx = RadarTestContext(job_runtime=runtime, default_runtime=False)
    fixed_now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    ctx.service.clock = lambda: fixed_now
    owner = uuid4()
    profile, _ = ctx.service.create_profile(
        owner_id=owner,
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
    paused, _ = ctx.service.set_status(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        status="paused",
        correlation_id=uuid4(),
    )
    runtime.fail_next_submit = True

    resumed, reserved = ctx.service.set_status(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=paused.version,
        status="active",
        correlation_id=uuid4(),
    )

    assert resumed.status == "active"
    assert reserved is not None
    assert reserved.trigger == "resumed"
    assert reserved.job_execution_id is None
    version_id = resumed.current_version_id
    assert version_id is not None
    version = ctx.versions.get(version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=resumed, version=version, trigger="resumed"
    )
    assert retried is not None
    assert retried.run_id == reserved.run_id
    assert retried.job_execution_id is not None


def test_resume_succeeds_when_reservation_and_recovery_store_are_unavailable() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile, _ = ctx.service.create_profile(
        owner_id=owner,
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
    paused, _ = ctx.service.set_status(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        status="paused",
        correlation_id=uuid4(),
    )
    ctx.runs.fail_next_reserve = True
    ctx.runs.fail_next_get_reserved = True

    resumed, scheduled = ctx.service.set_status(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=paused.version,
        status="active",
        correlation_id=uuid4(),
    )

    assert scheduled is None
    assert resumed.status == "active"
    assert resumed.current_version_id is not None
    version = ctx.versions.get(resumed.current_version_id)
    assert version is not None
    retried = ctx.service.schedule_version_run(
        profile=resumed, version=version, trigger="resumed"
    )
    assert retried is not None
    assert retried.job_execution_id is not None


def test_schedule_version_run_skips_paused_profile() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner, status="paused")
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )

    assert (
        ctx.service.schedule_version_run(
            profile=updated, version=version, trigger="edited"
        )
        is None
    )
    assert ctx.runs.rows == {}


def test_static_scheduler_rejects_a_label_other_than_the_loaded_baseline() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    updated, version = ctx.service.version_profile(
        owner_id=owner,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={},
        correlation_id=uuid4(),
    )
    ctx.service.score_policy_version = "scoring-baseline-v2"

    with pytest.raises(RadarStateError, match="does not match"):
        ctx.service.schedule_version_run(
            profile=updated,
            version=version,
            trigger="edited",
        )

    assert ctx.runs.rows == {}


def test_bump_profile_version_rejects_cross_owner() -> None:
    ctx = RadarTestContext()
    profile = build_profile(owner_id=uuid4())
    ctx.profiles.insert(profile)
    try:
        ctx.service.bump_profile_version(
            owner_id=uuid4(),
            profile_id=profile.profile_id,
            correlation_id=uuid4(),
        )
        raise AssertionError("expected RadarNotAccessible")
    except RadarNotAccessible:
        pass


def test_submit_run_creates_a_pending_edited_run() -> None:
    ctx = RadarTestContext()
    owner = uuid4()
    profile = build_profile(owner_id=owner)
    ctx.profiles.insert(profile)
    _, version = ctx.service.bump_profile_version(
        owner_id=owner,
        profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    run = ctx.service.submit_run(profile, version, trigger="edited")
    assert run is not None
    assert run.trigger == "edited"
    assert run.state == "pending"
    assert run.profile_version_id == version.version_id
    persisted = ctx.runs.get(run.run_id)
    assert persisted is not None and persisted.profile_version_id == version.version_id
