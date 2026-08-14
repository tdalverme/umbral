"""RadarService learning seams: bump_profile_version and submit_run (H3.3)."""

from __future__ import annotations

from uuid import uuid4

from tests.support.radar import RadarTestContext, build_profile

from umbral.application.radar.contracts import RadarNotAccessible


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
