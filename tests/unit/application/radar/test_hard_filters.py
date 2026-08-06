"""Pure hard filter behavior over golden unknown-value cases."""

from __future__ import annotations

from typing import cast

from tests.support.radar import build_listing, build_profile

from umbral.application.radar.hard_filters import (
    CandidateListing,
    apply_hard_filters,
)


def test_price_unknown_is_excluded() -> None:
    profile = build_profile()
    listing = build_listing(total_cost=700.0)
    assert apply_hard_filters(listing, profile)
    assert not apply_hard_filters(build_listing(neighborhood=None), profile)


def test_location_unknown_or_outside_zones_is_excluded() -> None:
    profile = build_profile(zones=("palermo",))
    assert apply_hard_filters(build_listing(neighborhood="PALERMO"), profile)
    assert not apply_hard_filters(build_listing(neighborhood=None), profile)
    assert not apply_hard_filters(build_listing(neighborhood="recoleta"), profile)


def test_rooms_unknown_included_but_below_minimum_excluded() -> None:
    profile = build_profile(min_rooms=2)
    assert apply_hard_filters(build_listing(rooms=None), profile)
    assert apply_hard_filters(build_listing(rooms=2), profile)
    assert not apply_hard_filters(build_listing(rooms=1), profile)


def test_rooms_no_minimum_always_passes_rooms_dimension() -> None:
    profile = build_profile(min_rooms=0)
    assert apply_hard_filters(build_listing(rooms=None), profile)
    assert apply_hard_filters(build_listing(rooms=1), profile)


def test_budget_above_cap_is_excluded() -> None:
    profile = build_profile(budget_max=1000.0)
    assert apply_hard_filters(build_listing(total_cost=1000.0), profile)
    assert not apply_hard_filters(build_listing(total_cost=1000.01), profile)


def test_operation_mismatch_is_excluded() -> None:
    profile = build_profile()

    class OtherOperationListing:
        operation = "sale"
        total_cost = 700.0
        neighborhood = "palermo"
        rooms = 2

    assert not apply_hard_filters(
        cast(CandidateListing, OtherOperationListing()), profile
    )


def test_rooms_exclude_strategy_rejects_unknown() -> None:
    from dataclasses import replace

    profile = build_profile(min_rooms=2)
    strategy = dict(profile.unknown_strategy)
    strategy["rooms"] = "exclude"
    profile = replace(profile, unknown_strategy=strategy)
    assert not apply_hard_filters(build_listing(rooms=None), profile)
