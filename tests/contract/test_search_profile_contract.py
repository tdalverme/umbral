"""Conformance of the search profile contract and its validator."""

from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.radar.golden import load_profiles_golden
from umbral.application.radar.profile_policy import (
    can_transition,
    default_unknown_strategy,
    parse_search_profile_policy,
    validate_profile,
)
from umbral.infrastructure.radar.contract_loader import load_search_profile_policy

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    ROOT / "contracts" / "search-profiles" / "v1" / "search-profile-policy.json"
)

POLICY = load_search_profile_policy(POLICY_PATH)


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    parsed = parse_search_profile_policy(published)
    assert parsed.contract_version == "1"
    assert parsed.policy_version == "search-profile-v1"
    assert len(parsed.neighborhoods) == 15
    assert parsed.unknown_strategies == {
        "price": "exclude",
        "location": "exclude",
        "rooms": "include",
        "surface": "include",
    }


def test_all_golden_profile_cases_validate_as_declared() -> None:
    for case in load_profiles_golden():
        errors = validate_profile(case["profile"], POLICY)
        expected = set(case["expected"].get("error_codes", []))
        assert set(errors) == expected, case["id"]


def test_default_unknown_strategy_is_explicit_per_filter() -> None:
    strategy = default_unknown_strategy(POLICY)
    assert set(strategy) == {"price", "location", "rooms", "surface"}
    assert all(value in {"exclude", "include"} for value in strategy.values())


def test_state_transitions_follow_the_contract() -> None:
    assert can_transition(POLICY, "active", "paused")
    assert can_transition(POLICY, "paused", "active")
    assert can_transition(POLICY, "active", "archived")
    assert can_transition(POLICY, "paused", "archived")
    assert not can_transition(POLICY, "archived", "active")
    assert not can_transition(POLICY, "archived", "paused")


def test_unknown_zone_and_budget_bounds_are_rejected() -> None:
    errors = validate_profile(
        {
            "name": "X",
            "zones": ["palermo", "no_existe"],
            "budget_max": 1000,
            "budget_min": 2000,
            "min_rooms": -1,
            "surface_min": 100,
            "surface_max": 50,
            "status": "active",
        },
        POLICY,
    )
    assert "radar.zone_unknown" in errors
    assert "radar.budget_range" in errors
    assert "radar.rooms_range" in errors
    assert "radar.surface_range" in errors
