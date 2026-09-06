"""HTTP schemas preserve legacy payloads while allowing partial radars."""

from dataclasses import replace
from uuid import uuid4

from tests.support.radar import RadarTestContext, build_profile

from umbral.api.routers import search_profiles
from umbral.api.routers.search_profiles import (
    CreateSearchProfileRequest,
    SearchProfileResponse,
    UpdateSearchProfileRequest,
)


def test_create_request_defaults_to_an_open_partial_profile() -> None:
    body = CreateSearchProfileRequest(name="Nueva búsqueda")

    assert body.zones == []
    assert body.budget_max is None
    assert body.min_rooms is None


def test_profile_response_exposes_absent_constraints_as_null() -> None:
    profile = build_profile(zones=(), budget_max=None, min_rooms=None)

    response = SearchProfileResponse.from_domain(profile)

    assert response.budget_max is None
    assert response.min_rooms is None


def test_update_distinguishes_an_explicit_null_from_an_omitted_constraint() -> None:
    clear_budget = UpdateSearchProfileRequest(budget_max=None)
    no_changes = UpdateSearchProfileRequest()

    assert search_profiles._profile_changes(clear_budget) == {"budget_max": None}
    assert search_profiles._profile_changes(no_changes) == {}


def test_profile_response_exposes_result_version_and_refresh_state() -> None:
    context = RadarTestContext()
    profile, run = context.service.create_profile(
        owner_id=uuid4(),
        name="Radar",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )

    assert run is not None
    response = SearchProfileResponse.from_domain(profile, run)

    assert response.current_version_id == profile.current_version_id
    assert response.latest_run is not None
    assert response.latest_run.profile_version_id == run.profile_version_id
    assert response.refresh_state == "refreshing"

    stale_profile = replace(profile, current_version_id=uuid4(), version=2)
    stale_response = SearchProfileResponse.from_domain(stale_profile, run)
    assert stale_response.refresh_state == "refreshing"
