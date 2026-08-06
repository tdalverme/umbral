"""RadarService profile administration: transitions, versioning, concurrency."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.support.radar import RadarTestContext

from umbral.application.radar.contracts import (
    RadarNotAccessible,
    RadarStateError,
    SearchProfile,
)
from umbral.domain.errors import ConcurrencyConflict

OWNER = uuid4()


def _create(ctx: RadarTestContext, name: str = "Radar") -> SearchProfile:
    profile, _ = ctx.service.create_profile(
        owner_id=OWNER,
        name=name,
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=2,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    return profile


def test_list_distinguishes_statuses_and_ownership() -> None:
    ctx = RadarTestContext()
    active = _create(ctx, "Activo")
    ctx.service.set_status(
        owner_id=OWNER,
        profile_id=active.profile_id,
        expected_version=active.version,
        status="paused",
        correlation_id=uuid4(),
    )
    listed = ctx.service.list_profiles(OWNER, None)
    assert [profile.name for profile in listed] == ["Activo"]
    assert ctx.service.list_profiles(OWNER, "paused")
    assert ctx.service.list_profiles(uuid4(), None) == ()


def test_pause_resume_and_archive_transitions() -> None:
    ctx = RadarTestContext()
    profile = _create(ctx)
    paused, _ = ctx.service.set_status(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        status="paused",
        correlation_id=uuid4(),
    )
    assert paused.status == "paused"
    resumed, run = ctx.service.set_status(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=paused.version,
        status="active",
        correlation_id=uuid4(),
    )
    assert resumed.status == "active"
    assert run is not None and run.trigger == "resumed"
    archived, _ = ctx.service.set_status(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=resumed.version,
        status="archived",
        correlation_id=uuid4(),
    )
    assert archived.status == "archived"
    with pytest.raises(RadarStateError):
        ctx.service.set_status(
            owner_id=OWNER,
            profile_id=profile.profile_id,
            expected_version=archived.version,
            status="active",
            correlation_id=uuid4(),
        )


def test_stale_version_raises_typed_concurrency_conflict() -> None:
    ctx = RadarTestContext()
    profile = _create(ctx)
    with pytest.raises(ConcurrencyConflict) as excinfo:
        ctx.service.update_profile(
            owner_id=OWNER,
            profile_id=profile.profile_id,
            expected_version=99,
            changes={"name": "Nuevo"},
            correlation_id=uuid4(),
        )
    assert excinfo.value.expected_version == 99
    assert excinfo.value.actual_version == profile.version


def test_edit_active_creates_version_and_triggers_edited_run() -> None:
    ctx = RadarTestContext()
    profile = _create(ctx)
    updated, run = ctx.service.update_profile(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"name": "Nuevo nombre", "budget_max": 1500.0},
        correlation_id=uuid4(),
    )
    assert updated.version == profile.version + 1
    assert updated.name == "Nuevo nombre"
    current_version_id = updated.current_version_id
    assert current_version_id is not None
    version = ctx.versions.get(current_version_id)
    assert version is not None
    assert version.profile_version == 2
    assert version.payload["budget_max"] == 1500.0
    assert run is not None and run.trigger == "edited"
    old_version_id = profile.current_version_id
    assert old_version_id is not None
    old_version = ctx.versions.rows[old_version_id]
    assert old_version.payload["name"] == "Radar"


def test_edit_paused_does_not_trigger_a_run() -> None:
    ctx = RadarTestContext()
    profile = _create(ctx)
    paused, _ = ctx.service.set_status(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        status="paused",
        correlation_id=uuid4(),
    )
    updated, run = ctx.service.update_profile(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=paused.version,
        changes={"name": "Pausado editado"},
        correlation_id=uuid4(),
    )
    assert run is None
    assert updated.status == "paused"


def test_archived_profiles_cannot_be_edited() -> None:
    ctx = RadarTestContext()
    profile = _create(ctx)
    archived, _ = ctx.service.set_status(
        owner_id=OWNER,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        status="archived",
        correlation_id=uuid4(),
    )
    with pytest.raises(RadarStateError):
        ctx.service.update_profile(
            owner_id=OWNER,
            profile_id=profile.profile_id,
            expected_version=archived.version,
            changes={"name": "No"},
            correlation_id=uuid4(),
        )


def test_cross_user_access_is_rejected() -> None:
    ctx = RadarTestContext()
    profile = _create(ctx)
    with pytest.raises(RadarNotAccessible):
        ctx.service.get_profile(uuid4(), profile.profile_id)
    with pytest.raises(RadarNotAccessible):
        ctx.service.update_profile(
            owner_id=uuid4(),
            profile_id=profile.profile_id,
            expected_version=profile.version,
            changes={"name": "Ajeno"},
            correlation_id=uuid4(),
        )
