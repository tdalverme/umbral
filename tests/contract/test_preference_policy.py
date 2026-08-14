"""Conformance of preference, scoring, and partial-profile policies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]


def _load_json(relative_path: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    )


def test_preference_policy_has_explicit_authority_and_confirmation_rules() -> None:
    """Weak or passive signals must not override explicit preference evidence."""
    policy = _load_json("contracts/preferences/v1/preference-policy-v1.json")

    assert policy["contract_version"] == "1"
    assert policy["authority_order"] == ["explicit", "deliberate_feedback", "passive"]
    assert policy["auto_apply"] == [
        "soft_add",
        "soft_revise",
        "soft_withdraw",
        "open_location",
    ]
    assert policy["require_confirmation"] == [
        "hard_filter",
        "material_contradiction",
        "irreversible_delete",
    ]


def test_semantic_preferences_are_soft_capped_and_evidence_bound() -> None:
    """A semantic signal without compatible evidence must not affect ranking."""
    preference_policy = _load_json("contracts/preferences/v1/preference-policy-v1.json")
    scoring_policy = _load_json("contracts/scoring/v2/scoring-policy-v2.json")

    expected_semantic = {
        "mode": "soft",
        "max_weight": 0.10,
        "missing_evidence_contribution": 0.0,
    }
    assert preference_policy["semantic"] == expected_semantic
    assert scoring_policy["semantic"] == expected_semantic


def test_search_profile_policy_v2_keeps_caba_rentals_partial_and_open() -> None:
    """Requiring a zone or budget would reject a valid first conversational turn."""
    policy = _load_json("contracts/search-profiles/v2/search-profile-policy-v2.json")

    assert policy["contract_version"] == "2"
    assert policy["policy_version"] == "search-profile-v2"
    assert policy["operation"] == ["rental"]
    assert policy["scope"] == {"city": "caba", "residential_only": True}
    assert policy["limits"]["zones_min"] == 0
    assert policy["nullable_constraints"] == [
        "budget_max",
        "budget_min",
        "min_rooms",
        "surface_min",
        "surface_max",
    ]
