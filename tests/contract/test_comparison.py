"""Conformance of the structured comparison builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from umbral.application.radar.contracts import RecommendationItem, SearchProfile
from umbral.application.scoring.comparison import build_comparison
from umbral.application.scoring.contracts import CriterionEvaluation
from umbral.application.scoring.policy import parse_policy_document
from umbral.application.silver.contracts import (
    NormalizedListing,
    SourceIdentity,
)
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import load_scoring_policy_seed

GOLDEN = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "scoring"
        / "comparison-golden.json"
    ).read_text(encoding="utf-8")
)

MATCHER_TYPES = load_matcher_types()
POLICY = parse_policy_document(load_scoring_policy_seed(), MATCHER_TYPES)


def _profile(profile_id: UUID) -> SearchProfile:
    return SearchProfile(
        profile_id=profile_id,
        owner_id=uuid4(),
        name="radar",
        operation="rental",
        zones=("palermo", "recoleta"),
        budget_max=600000,
        budget_min=None,
        min_rooms=2,
        surface_min=40,
        surface_max=80,
        status="active",
        unknown_strategy={},
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_version_id=None,
        latest_run_id=None,
        correlation_id=uuid4(),
    )


def _listing(case: Mapping[str, object]) -> NormalizedListing:
    return NormalizedListing(
        listing_id=UUID(str(case["listing_id"])),
        canonical_property_id=uuid4(),
        run_id=uuid4(),
        snapshot_id=uuid4(),
        source=SourceIdentity(
            source_id="source-a", source_version="v1", contract_version="1"
        ),
        external_id=str(case["listing_id"]),
        url=None,
        published_at=datetime.now(timezone.utc),
        last_observed_at=datetime.now(timezone.utc),
        normalizer_version="silver-v1",
        operation="rental",
        property_type="apartment",
        price_value=float(case["total_cost"]),
        price_currency="ARS",
        expenses_value=case["expenses_value"],
        expenses_currency="ARS",
        total_cost=float(case["total_cost"]),
        price_assumptions={},
        surface_m2=case["surface_m2"],
        rooms=case["rooms"],
        bedrooms=case["bedrooms"],
        floor=3,
        amenities=(),
        description_text="",
        location_text="",
        neighborhood=case["neighborhood"],
        geo_precision=case["geo_precision"],  # type: ignore[arg-type]
        geometry=None,
        geo_source="fixture",
        normalization_errors=(),
    )


def _item(listing_id: UUID, position: int, score: float) -> RecommendationItem:
    return RecommendationItem(
        item_id=uuid4(),
        run_id=uuid4(),
        listing_id=listing_id,
        score=score,
        position=position,
        contributions={},
    )


def _evaluation(
    listing_id: UUID, criterion_key: str, case: Mapping[str, object]
) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=uuid4(),
        listing_id=listing_id,
        criterion_key=criterion_key,
        criterion_version="policy:scoring-policy-v1",
        matcher_type="semantic_feature",
        params={},
        input_refs=(),
        score=float(case["score"]),
        confidence=float(case["confidence"]),
        state=case["state"],  # type: ignore[arg-type]
        contribution=0.0,
        reason_code=str(case["reason_code"]),
        evidence_refs=tuple(dict(ref) for ref in case["evidence_refs"]),
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def test_golden_comparison_case_matches() -> None:
    case = GOLDEN["cases"][0]
    profile_id = uuid4()
    run_id = uuid4()
    listings = [_listing(item) for item in case["listings"]]
    items = tuple(
        _item(
            UUID(str(item["listing_id"])), int(item["position"]), float(item["score"])
        )
        for item in case["listings"]
    )
    evaluations: dict[UUID, dict[str, CriterionEvaluation]] = {}
    for listing_id, by_concept in case["evaluations"].items():
        evaluations[UUID(listing_id)] = {
            key: _evaluation(UUID(listing_id), key, value)
            for key, value in by_concept.items()
        }
    comparison = build_comparison(
        profile=_profile(profile_id),
        run_id=run_id,
        score_version=case["score_version"],
        limit=int(case["limit"]),
        items=items,
        listings_by_id={listing.listing_id: listing for listing in listings},
        evaluations=evaluations,
        policy=POLICY,
    )
    expected = case["expected"]
    assert [d.key for d in comparison.dimensions if d.kind == "fixed"] == expected[
        "fixed_dimension_keys"
    ]
    assert [d.key for d in comparison.dimensions if d.kind == "criterion"] == expected[
        "criterion_dimension_keys"
    ]
    missing = {
        (str(cell.listing_id), cell.dimension_key)
        for cell in comparison.cells
        if cell.missing
    }
    assert missing == {tuple(pair) for pair in expected["missing_cells"]}
    unknown = {
        (str(cell.listing_id), cell.dimension_key)
        for cell in comparison.cells
        if cell.state == "unknown" and not cell.missing
    }
    assert unknown == {tuple(pair) for pair in expected["unknown_cells"]}
    assert expected["no_winner"] is True


def test_comparison_never_produces_a_winner() -> None:
    case = GOLDEN["cases"][0]
    profile_id = uuid4()
    run_id = uuid4()
    listings = [_listing(item) for item in case["listings"]]
    items = tuple(
        _item(
            UUID(str(item["listing_id"])), int(item["position"]), float(item["score"])
        )
        for item in case["listings"]
    )
    comparison = build_comparison(
        profile=_profile(profile_id),
        run_id=run_id,
        score_version="scoring-policy-v1",
        limit=6,
        items=items,
        listings_by_id={listing.listing_id: listing for listing in listings},
        evaluations={},
        policy=POLICY,
    )
    for cell in comparison.cells:
        assert cell.dimension_key != "winner"
