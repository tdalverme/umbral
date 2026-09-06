from __future__ import annotations

from uuid import uuid4

from tests.support.radar import RadarTestContext

from umbral.api.routers.matches import MatchesResponse


def test_matches_response_exposes_result_version_and_refresh_state() -> None:
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
    response = MatchesResponse.from_domain(
        profile.profile_id,
        run,
        (),
        None,
        current_version_id=profile.current_version_id,
    )

    assert response.profile_version_id == run.profile_version_id
    assert response.current_version_id == profile.current_version_id
    assert response.refresh_state == "refreshing"
