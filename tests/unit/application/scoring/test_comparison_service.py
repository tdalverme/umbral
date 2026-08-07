"""Unit tests for structured comparison (US8)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_item,
    build_run,
)

from umbral.application.scoring.contracts import (
    ComparisonDuplicateListing,
    ComparisonLimitExceeded,
    ComparisonNotInRadar,
    CriterionEvaluation,
    ExplanationUnavailable,
)


def _context_with_run() -> tuple[
    ScoringTestContext, object, object, tuple[object, object]
]:
    context = ScoringTestContext()
    owner_id = uuid4()
    profile_id = uuid4()
    run_id = uuid4()
    first = build_listing(total_cost=450000)
    second = build_listing(total_cost=480000)
    run = build_run(profile_id=profile_id, profile_version_id=uuid4(), run_id=run_id)
    context.runs.rows[run_id] = run
    context.items.items_by_run[run_id] = [
        build_item(run_id, first.listing_id, position=0),
        build_item(run_id, second.listing_id, position=1),
    ]
    context.listings.rows[first.listing_id] = first
    context.listings.rows[second.listing_id] = second
    profile = build_profile(owner_id=owner_id, profile_id=profile_id)
    context.profiles.rows[profile_id] = profile
    for listing in (first, second):
        context.evaluations.rows.append(
            CriterionEvaluation(
                evaluation_id=uuid4(),
                run_id=run_id,
                listing_id=listing.listing_id,
                criterion_key="presupuesto",
                criterion_version="policy:scoring-policy-v1",
                matcher_type="numeric_range",
                params={},
                input_refs=(),
                score=0.3,
                confidence=1.0,
                state="match",
                contribution=0.075,
                reason_code="budget_within_headroom",
                evidence_refs=(
                    {
                        "kind": "listing_field",
                        "ref": "total_cost",
                        "version": "silver-v1",
                    },
                ),
                created_at=datetime.now(timezone.utc),
                correlation_id=uuid4(),
            )
        )
    return context, owner_id, profile_id, (first.listing_id, second.listing_id)


def test_comparison_builds_matrix_with_fixed_and_criterion_dimensions() -> None:
    context, owner_id, profile_id, (first, second) = _context_with_run()
    comparison = context.service.build_comparison(
        owner_id=owner_id, profile_id=profile_id, listing_ids=(first, second)
    )
    assert comparison.limit == 6
    fixed_keys = [d.key for d in comparison.dimensions if d.kind == "fixed"]
    assert "total_cost" in fixed_keys and "score" in fixed_keys
    criterion_keys = [d.key for d in comparison.dimensions if d.kind == "criterion"]
    assert "presupuesto" not in criterion_keys  # presupuesto is fixed
    assert "balcon" in criterion_keys
    assert len(comparison.cells) == len(comparison.listings) * len(
        comparison.dimensions
    )


def test_more_than_limit_is_rejected() -> None:
    context, owner_id, profile_id, (first, second) = _context_with_run()
    with pytest.raises(ComparisonLimitExceeded):
        context.service.build_comparison(
            owner_id=owner_id,
            profile_id=profile_id,
            listing_ids=(first, second, uuid4(), uuid4(), uuid4(), uuid4(), uuid4()),
        )


def test_single_listing_is_rejected() -> None:
    context, owner_id, profile_id, (first, _) = _context_with_run()
    with pytest.raises(ComparisonLimitExceeded):
        context.service.build_comparison(
            owner_id=owner_id, profile_id=profile_id, listing_ids=(first,)
        )


def test_duplicate_listings_are_rejected() -> None:
    context, owner_id, profile_id, (first, _) = _context_with_run()
    with pytest.raises(ComparisonDuplicateListing):
        context.service.build_comparison(
            owner_id=owner_id, profile_id=profile_id, listing_ids=(first, first)
        )


def test_listing_outside_the_run_is_rejected() -> None:
    context, owner_id, profile_id, (first, _) = _context_with_run()
    with pytest.raises(ComparisonNotInRadar):
        context.service.build_comparison(
            owner_id=owner_id, profile_id=profile_id, listing_ids=(first, uuid4())
        )


def test_legacy_run_has_no_comparison() -> None:
    context, owner_id, profile_id, (first, second) = _context_with_run()
    run = context.runs.latest_succeeded_for_profile(profile_id)
    assert run is not None
    context.runs.rows[run.run_id] = build_run(
        profile_id=profile_id,
        profile_version_id=run.profile_version_id,
        score_policy_version="scoring-baseline-v1",
        run_id=run.run_id,
    )
    with pytest.raises(ExplanationUnavailable):
        context.service.build_comparison(
            owner_id=owner_id, profile_id=profile_id, listing_ids=(first, second)
        )


def test_cross_owner_comparison_is_denied() -> None:
    context, _, profile_id, (first, second) = _context_with_run()
    with pytest.raises(Exception):
        context.service.build_comparison(
            owner_id=uuid4(), profile_id=profile_id, listing_ids=(first, second)
        )
