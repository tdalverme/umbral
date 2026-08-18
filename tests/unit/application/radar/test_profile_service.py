"""RadarService profile creation flow."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from tests.support.radar import RadarTestContext

from umbral.application.radar.contracts import (
    RadarValidationError,
    RecommendationRun,
    SearchProfile,
)

OWNER = uuid4()


def _create(
    ctx: RadarTestContext, **overrides: Any
) -> tuple[SearchProfile, RecommendationRun | None]:
    kwargs: dict[str, Any] = {
        "owner_id": OWNER,
        "name": "Mi depto",
        "zones": ("palermo",),
        "budget_max": 1000.0,
        "budget_min": None,
        "min_rooms": 2,
        "surface_min": None,
        "surface_max": None,
        "unknown_strategy": None,
        "correlation_id": uuid4(),
    }
    kwargs.update(overrides)
    return ctx.service.create_profile(**kwargs)


def test_create_persists_profile_version_event_and_run() -> None:
    ctx = RadarTestContext()
    profile, run = _create(ctx)
    assert profile.version == 1
    assert profile.status == "active"
    assert profile.current_version_id is not None
    persisted_profile = ctx.profiles.get(profile.profile_id)
    assert persisted_profile is not None
    assert persisted_profile.current_version_id == profile.current_version_id

    version = ctx.versions.get(profile.current_version_id)
    assert version is not None
    assert version.profile_version == 1
    assert version.payload["zones"] == ["palermo"]

    created_events = [
        event for event in ctx.events.events if event.event_type == "radar.created.v1"
    ]
    assert len(created_events) == 1
    assert created_events[0].payload["search_profile_id"] == str(profile.profile_id)

    assert run is not None
    assert run.state == "pending"
    assert run.trigger == "created"
    assert run.job_execution_id is not None
    persisted = ctx.runs.get(run.run_id)
    assert persisted is not None
    assert persisted.profile_version_id == version.version_id


def test_create_without_job_runtime_submits_no_run() -> None:
    ctx = RadarTestContext(default_runtime=False)
    profile, run = _create(ctx)
    assert run is None
    assert profile.version == 1


def test_create_partial_profile_is_active_without_constraints() -> None:
    ctx = RadarTestContext()

    profile, run = _create(
        ctx,
        name="Nueva búsqueda",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
    )

    assert profile.status == "active"
    assert profile.zones == ()
    assert profile.budget_max is None
    assert profile.min_rooms is None
    assert run is not None
    assert run.trigger == "created"


def test_create_with_invalid_profile_is_rejected_without_persistence() -> None:
    ctx = RadarTestContext()
    with pytest.raises(RadarValidationError) as excinfo:
        _create(ctx, zones=("fuera_de_caba",), budget_min=2000.0)
    assert "radar.zone_unknown" in excinfo.value.error_codes
    assert ctx.profiles.rows == {}
    assert ctx.versions.rows == {}
    assert ctx.events.events == []


def test_create_audit_failure_rolls_back_profile_snapshot_and_event() -> None:
    ctx = RadarTestContext()
    ctx.profiles.fail_next_atomic_insert = True

    with pytest.raises(RuntimeError, match="atomic create unavailable"):
        _create(ctx)

    assert ctx.profiles.rows == {}
    assert ctx.versions.rows == {}
    assert ctx.events.events == []


def test_partial_profile_rejects_non_positive_budget_with_v2_error() -> None:
    ctx = RadarTestContext()

    with pytest.raises(RadarValidationError) as excinfo:
        _create(ctx, budget_max=0)

    assert excinfo.value.error_codes == ("radar.budget_range",)


def test_create_uses_versioned_default_unknown_strategy() -> None:
    ctx = RadarTestContext()
    profile, _ = _create(ctx)
    assert profile.unknown_strategy == {
        "price": "exclude",
        "location": "exclude",
        "rooms": "include",
        "surface": "include",
    }


def test_repeated_create_dispatches_identity_stable_runs() -> None:
    ctx = RadarTestContext()
    first_profile, first_run = _create(ctx, name="Uno")
    second_profile, second_run = _create(ctx, name="Dos")
    assert first_profile.profile_id != second_profile.profile_id
    assert first_run is not None and second_run is not None
    assert first_run.run_id != second_run.run_id
