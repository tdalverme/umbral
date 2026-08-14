"""Unit tests for deterministic explanations (US6, US7)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from tests.support.radar import profile_version_payload
from tests.support.scoring import (
    ScoringTestContext,
    build_item,
    build_run,
)

from umbral.application.radar.contracts import ProfileVersion
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    ExplanationUnavailable,
    ScoringNotAccessible,
    ScoringNotFound,
    ScoringStateError,
)


def _evaluation(
    run_id: UUID,
    listing_id: UUID,
    score_policy_version: str,
    criterion_key: str = "presupuesto",
) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=run_id,
        listing_id=listing_id,
        criterion_key=criterion_key,
        criterion_version=f"policy:{score_policy_version}",
        matcher_type="numeric_range",
        params={},
        input_refs=(),
        score=0.3,
        confidence=1.0,
        state="match",
        contribution=0.075,
        reason_code="budget_within_headroom",
        evidence_refs=(
            {"kind": "listing_field", "ref": "total_cost", "version": "silver-v1"},
        ),
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def _context_with_run() -> tuple[ScoringTestContext, UUID, UUID, UUID, UUID]:
    context = ScoringTestContext()
    owner_id = uuid4()
    profile_id = uuid4()
    listing_id = uuid4()
    run_id = uuid4()
    profile_version_id = uuid4()
    score_policy_version = context.service.pin_policy_version()
    run = build_run(
        profile_id=profile_id,
        profile_version_id=profile_version_id,
        run_id=run_id,
        score_policy_version=score_policy_version,
    )
    context.runs.rows[run_id] = run
    context.items.items_by_run[run_id] = [build_item(run_id, listing_id)]
    context.evaluations.rows.append(
        _evaluation(run_id, listing_id, score_policy_version)
    )
    from tests.support.radar import build_profile

    profile = build_profile(owner_id=owner_id, profile_id=profile_id)
    context.profiles.rows[profile_id] = profile
    context.versions.rows[profile_version_id] = ProfileVersion(
        version_id=profile_version_id,
        profile_id=profile_id,
        profile_version=1,
        payload=profile_version_payload(profile),
        created_at=profile.created_at,
        correlation_id=profile.correlation_id,
    )
    return context, owner_id, profile_id, run_id, listing_id


def test_get_explanation_returns_breakdown_with_evidence() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    explanation = context.service.get_explanation(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )
    assert explanation.score_version == context.runs.rows[run_id].score_policy_version
    assert explanation.run_id == run_id
    assert explanation.listing_id == listing_id
    assert any(reason.criterion_key == "presupuesto" for reason in explanation.reasons)
    assert all(reason.evidence_refs for reason in explanation.reasons)
    assert "budget_max" in explanation.satisfied_filters
    assert (
        explanation.profile_snapshot["policy_version_id"]
        == context.runs.rows[run_id].score_policy_version
    )


def test_explanations_keep_the_run_v1_filters_after_profile_v2_opens() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    from tests.support.radar import build_profile

    context.profiles.rows[profile_id] = build_profile(
        owner_id=owner_id,
        profile_id=profile_id,
        zones=(),
        budget_max=None,
        min_rooms=None,
    )

    explanation = context.service.get_explanation(
        owner_id=owner_id,
        profile_id=profile_id,
        run_id=run_id,
        listing_id=listing_id,
    )

    page = context.service.list_explanations(
        owner_id=owner_id,
        profile_id=profile_id,
        run_id=run_id,
        after_position=None,
        limit=10,
    )

    assert explanation.satisfied_filters == ("budget_max", "zones", "min_rooms")
    assert page[0].satisfied_filters == ("budget_max", "zones", "min_rooms")


def test_explanation_fails_when_the_run_policy_revision_is_missing() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    context.policies.rows.clear()

    with pytest.raises(ScoringNotFound, match="policy version not found"):
        context.service.get_explanation(
            owner_id=owner_id,
            profile_id=profile_id,
            run_id=run_id,
            listing_id=listing_id,
        )


def test_explanation_rejects_a_version_owned_by_another_profile() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    run = context.runs.rows[run_id]
    version = context.versions.rows[run.profile_version_id]
    context.versions.rows[version.version_id] = replace(
        version,
        profile_id=uuid4(),
    )

    with pytest.raises(ScoringStateError, match="does not belong"):
        context.service.get_explanation(
            owner_id=owner_id,
            profile_id=profile_id,
            run_id=run_id,
            listing_id=listing_id,
        )


def test_two_calls_produce_identical_explanation() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    first = context.service.get_explanation(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )
    second = context.service.get_explanation(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )
    assert first == second


def test_legacy_run_raises_explanation_unavailable() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    context.runs.rows[run_id] = build_run(
        profile_id=profile_id,
        profile_version_id=context.runs.rows[run_id].profile_version_id,
        score_policy_version="scoring-baseline-v1",
        run_id=run_id,
    )
    with pytest.raises(ExplanationUnavailable):
        context.service.get_explanation(
            owner_id=owner_id,
            profile_id=profile_id,
            run_id=run_id,
            listing_id=listing_id,
        )


def test_cross_owner_access_is_denied() -> None:
    context, _, profile_id, run_id, listing_id = _context_with_run()
    with pytest.raises(ScoringNotAccessible):
        context.service.get_explanation(
            owner_id=uuid4(),
            profile_id=profile_id,
            run_id=run_id,
            listing_id=listing_id,
        )


def test_listing_outside_the_run_is_not_found() -> None:
    context, owner_id, profile_id, run_id, _ = _context_with_run()
    with pytest.raises(ScoringNotFound):
        context.service.get_explanation(
            owner_id=owner_id,
            profile_id=profile_id,
            run_id=run_id,
            listing_id=uuid4(),
        )


def test_list_explanations_paginates_without_mixing_versions() -> None:
    context, owner_id, profile_id, run_id, listing_id = _context_with_run()
    second = uuid4()
    context.items.items_by_run[run_id] = [
        build_item(run_id, listing_id, position=0),
        build_item(run_id, second, position=1),
    ]
    context.evaluations.rows.append(
        _evaluation(run_id, second, context.runs.rows[run_id].score_policy_version)
    )
    page = context.service.list_explanations(
        owner_id=owner_id,
        profile_id=profile_id,
        run_id=run_id,
        after_position=None,
        limit=1,
    )
    assert len(page) == 1
    assert all(
        item.score_version == context.runs.rows[run_id].score_policy_version
        for item in page
    )
    next_page = context.service.list_explanations(
        owner_id=owner_id,
        profile_id=profile_id,
        run_id=run_id,
        after_position=0,
        limit=1,
    )
    assert len(next_page) == 1
    assert {item.listing_id for item in page} != {item.listing_id for item in next_page}
