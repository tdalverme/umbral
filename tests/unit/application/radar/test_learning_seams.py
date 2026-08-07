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
