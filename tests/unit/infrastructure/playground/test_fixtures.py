from __future__ import annotations

from umbral.infrastructure.playground.fixtures import load_fixtures


def test_demo_fixture_contains_profile_listing_and_urban_data() -> None:
    demo = load_fixtures().by_id("demo")

    assert demo.profile["budget_max"] == 1200
    assert demo.listings[0]["id"] == "listing-palermo-001"
    assert demo.urban["features"]
