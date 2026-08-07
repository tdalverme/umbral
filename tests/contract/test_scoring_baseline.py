"""Conformance of the scoring baseline contract and its pure scoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from tests.fixtures.radar.golden import load_scoring_golden
from umbral.application.radar.contracts import SearchProfile
from umbral.application.radar.scoring import (
    compute_score,
    parse_scoring_baseline,
)
from umbral.application.silver.contracts import GeoPrecision
from umbral.infrastructure.radar.contract_loader import (
    load_scoring_baseline,
    load_search_profile_policy,
)

ROOT = Path(__file__).resolve().parents[2]
SCORING_PATH = ROOT / "contracts" / "scoring" / "v1" / "scoring-baseline.json"

SCORING = load_scoring_baseline(SCORING_PATH)
POLICY = load_search_profile_policy()


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(SCORING_PATH.read_text(encoding="utf-8"))
    parsed = parse_scoring_baseline(published)
    assert parsed.contract_version == "1"
    assert parsed.score_policy_version == "scoring-baseline-v1"
    assert parsed.weights == {
        "budget": 0.4,
        "rooms": 0.2,
        "surface": 0.2,
        "location_precision": 0.2,
    }
    assert parsed.tie_break == ("score desc", "total_cost asc", "listing_id asc")


def _profile_from(payload: Mapping[str, Any]) -> SearchProfile:
    return SearchProfile(
        profile_id=uuid4(),
        owner_id=uuid4(),
        name=str(payload["name"]),
        operation="rental",
        zones=tuple(str(zone) for zone in payload["zones"]),
        budget_max=float(payload["budget_max"]),
        budget_min=None,
        min_rooms=int(payload["min_rooms"]),
        surface_min=(
            float(payload["surface_min"]) if payload.get("surface_min") else None
        ),
        surface_max=(
            float(payload["surface_max"]) if payload.get("surface_max") else None
        ),
        status="active",
        unknown_strategy=dict(POLICY.unknown_strategies),
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_version_id=None,
        latest_run_id=None,
        correlation_id=uuid4(),
    )


def _listing_from(payload: Mapping[str, Any]) -> _Listing:
    return _Listing(
        listing_id=UUID(payload["listing_id"]) if "listing_id" in payload else uuid4(),
        total_cost=float(payload["total_cost"]),
        rooms=payload.get("rooms"),
        surface_m2=payload.get("surface_m2"),
        geo_precision=cast(GeoPrecision, str(payload["geo_precision"])),
    )


class _Listing:
    def __init__(
        self,
        *,
        listing_id: UUID,
        total_cost: float,
        rooms: int | None,
        surface_m2: float | None,
        geo_precision: GeoPrecision,
    ) -> None:
        self.listing_id = listing_id
        self.total_cost = total_cost
        self.rooms = rooms
        self.surface_m2 = surface_m2
        self.geo_precision = geo_precision


def test_all_golden_scoring_cases_match() -> None:
    for case in load_scoring_golden():
        profile = _profile_from(case["profile"])
        if "listing" in case:
            listing = _listing_from(case["listing"])
            score, contributions = compute_score(profile, listing, SCORING)
            assert score == case["expected"]["score"], case["id"]
            assert contributions == case["expected"]["contributions"], case["id"]
        else:
            scored = [
                (compute_score(profile, _listing_from(item), SCORING), item)
                for item in case["listings"]
            ]
            scored.sort(
                key=lambda pair: (
                    -pair[0][0],
                    pair[1]["total_cost"],
                    str(pair[1]["listing_id"]),
                )
            )
            ordered = [str(item["listing_id"]) for _, item in scored]
            assert ordered == case["expected"]["order"], case["id"]


def test_identical_inputs_produce_identical_scores() -> None:
    case = next(case for case in load_scoring_golden() if "listing" in case)
    profile = _profile_from(case["profile"])
    listing = _listing_from(case["listing"])
    first, first_contributions = compute_score(profile, listing, SCORING)
    second, second_contributions = compute_score(profile, listing, SCORING)
    assert first == second
    assert first_contributions == second_contributions
