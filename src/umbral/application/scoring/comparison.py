"""Pure structured comparison builder.

Compares listings of one run with homogeneous dimensions (fixed basics plus
the profile's active criteria), shows missing cells explicitly and never
invents a winner (FR-016/FR-017, US8.5).
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from umbral.application.radar.contracts import RecommendationItem, SearchProfile
from umbral.application.scoring.contracts import (
    Comparison,
    ComparisonCell,
    ComparisonDimension,
    CriterionEvaluation,
)
from umbral.application.scoring.policy import ScoringPolicyDoc, is_fixed_criterion
from umbral.application.silver.contracts import NormalizedListing

_FIXED_DIMENSIONS: tuple[ComparisonDimension, ...] = (
    ComparisonDimension("fixed", "total_cost", "precio total"),
    ComparisonDimension("fixed", "expenses", "expensas"),
    ComparisonDimension("fixed", "surface_m2", "superficie"),
    ComparisonDimension("fixed", "rooms", "ambientes"),
    ComparisonDimension("fixed", "bedrooms", "dormitorios"),
    ComparisonDimension("fixed", "location", "ubicacion / precision"),
    ComparisonDimension("fixed", "score", "score"),
)

EvaluationsByListing = Mapping[UUID, Mapping[str, CriterionEvaluation]]


def build_comparison(
    *,
    profile: SearchProfile,
    run_id: UUID,
    score_version: str,
    limit: int,
    items: tuple[RecommendationItem, ...],
    listings_by_id: Mapping[UUID, NormalizedListing],
    evaluations: EvaluationsByListing,
    policy: ScoringPolicyDoc,
) -> Comparison:
    """Build the matrix from validated inputs (limit and membership checked)."""

    dimensions = _FIXED_DIMENSIONS + tuple(
        ComparisonDimension(
            "criterion", criterion.key, criterion.key, concept=criterion.concept
        )
        for criterion in policy.criteria
        if not is_fixed_criterion(criterion.key)
    )
    cells: list[ComparisonCell] = []
    for item in items:
        listing = listings_by_id.get(item.listing_id)
        evaluation_by_key = evaluations.get(item.listing_id, {})
        for dimension in dimensions:
            cells.append(
                _cell(
                    item=item,
                    listing=listing,
                    evaluation=evaluation_by_key.get(dimension.key),
                    dimension=dimension,
                    item_score=item.score,
                )
            )
    return Comparison(
        search_profile_id=profile.profile_id,
        run_id=run_id,
        score_version=score_version,
        limit=limit,
        listings=tuple(
            {"listing_id": item.listing_id, "position": item.position} for item in items
        ),
        dimensions=dimensions,
        cells=tuple(cells),
    )


def _cell(
    *,
    item: RecommendationItem,
    listing: NormalizedListing | None,
    evaluation: CriterionEvaluation | None,
    dimension: ComparisonDimension,
    item_score: float,
) -> ComparisonCell:
    if dimension.kind == "criterion":
        if evaluation is None:
            return ComparisonCell(
                item.listing_id, dimension.key, None, "unknown", True, ()
            )
        return ComparisonCell(
            item.listing_id,
            dimension.key,
            evaluation.score,
            evaluation.state,
            False,
            evaluation.evidence_refs,
        )
    if dimension.key == "score":
        return ComparisonCell(
            item.listing_id, dimension.key, item_score, "match", False
        )
    if listing is None:
        return ComparisonCell(item.listing_id, dimension.key, None, "unknown", True)
    if dimension.key == "location":
        value = f"{listing.neighborhood or 'desconocido'} ({listing.geo_precision})"
        return ComparisonCell(item.listing_id, dimension.key, value, "match", False)
    field_value = {
        "total_cost": listing.total_cost,
        "expenses": listing.expenses_value,
        "surface_m2": listing.surface_m2,
        "rooms": listing.rooms,
        "bedrooms": listing.bedrooms,
    }.get(dimension.key)
    missing = field_value is None
    return ComparisonCell(
        item.listing_id,
        dimension.key,
        field_value,
        "unknown" if missing else "match",
        missing,
    )
