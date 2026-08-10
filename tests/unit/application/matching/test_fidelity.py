"""Unit tests for the pure fidelity evaluator."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.application.matching.fidelity import evaluate_fidelity
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    Explanation,
    ExplanationReason,
    ExplanationRisk,
)

_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _evaluation(
    criterion_key: str,
    *,
    state: str = "match",
    confidence: float = 1.0,
    evidence_refs: tuple[dict[str, object], ...] = (),
) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=uuid4(),
        listing_id=uuid4(),
        criterion_key=criterion_key,
        criterion_version="policy:scoring-policy-v1",
        matcher_type="categorical",
        params={},
        input_refs=evidence_refs,
        score=1.0,
        confidence=confidence,
        state=state,  # type: ignore[arg-type]
        contribution=0.1,
        reason_code="concept_observed",
        evidence_refs=evidence_refs,
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def _explanation(
    *,
    reasons: tuple[ExplanationReason, ...] = (),
    risks: tuple[ExplanationRisk, ...] = (),
    missing_data: tuple[str, ...] = (),
    score_version: str = "scoring-policy-v1",
) -> Explanation:
    return Explanation(
        search_profile_id=uuid4(),
        run_id=uuid4(),
        listing_id=uuid4(),
        score_version=score_version,
        score=0.8,
        confidence=0.8,
        reasons=reasons,
        risks=risks,
        missing_data=missing_data,
        satisfied_filters=("budget_max",),
        profile_snapshot={},
        feature_snapshot={},
    )


def test_supported_claim_passes() -> None:
    evidence: tuple[dict[str, object], ...] = (
        {"kind": "listing_field", "ref": "total_cost"},
    )
    breakdown = (_evaluation("presupuesto", evidence_refs=evidence),)
    reason = ExplanationReason(
        criterion_key="presupuesto",
        state="match",
        score=1.0,
        confidence=1.0,
        contribution=0.1,
        evidence_level="strong",
        reason_code="budget_within_headroom",
        evidence_refs=evidence,
        text="Dentro del presupuesto.",
    )
    report = evaluate_fidelity(
        explanation=_explanation(reasons=(reason,)), breakdown=breakdown
    )
    assert report.passing
    assert report.claims[0].verdict == "supported"


def test_claim_without_breakdown_entry_is_unsupported() -> None:
    breakdown = ()
    reason = ExplanationReason(
        criterion_key="balcon",
        state="match",
        score=1.0,
        confidence=1.0,
        contribution=0.1,
        evidence_level="strong",
        reason_code="concept_observed",
        evidence_refs=({"kind": "observation", "ref": "obs-1"},),
        text="Tiene balcon.",
    )
    report = evaluate_fidelity(
        explanation=_explanation(reasons=(reason,)), breakdown=breakdown
    )
    assert not report.passing
    assert report.claims[0].verdict == "unsupported"


def test_claim_without_evidence_is_unsupported() -> None:
    breakdown = (_evaluation("balcon", evidence_refs=()),)
    reason = ExplanationReason(
        criterion_key="balcon",
        state="match",
        score=1.0,
        confidence=1.0,
        contribution=0.1,
        evidence_level="strong",
        reason_code="concept_observed",
        evidence_refs=(),
        text="Tiene balcon.",
    )
    report = evaluate_fidelity(
        explanation=_explanation(reasons=(reason,)), breakdown=breakdown
    )
    assert not report.passing
    assert report.claims[0].verdict == "unsupported"


def test_contradicting_state_is_detected() -> None:
    breakdown = (_evaluation("balcon", state="mismatch"),)
    reason = ExplanationReason(
        criterion_key="balcon",
        state="match",
        score=1.0,
        confidence=1.0,
        contribution=0.1,
        evidence_level="strong",
        reason_code="concept_observed",
        evidence_refs=({"kind": "observation", "ref": "obs-1"},),
        text="Tiene balcon.",
    )
    report = evaluate_fidelity(
        explanation=_explanation(reasons=(reason,)), breakdown=breakdown
    )
    assert not report.passing
    assert report.claims[0].verdict == "contradiction"


def test_missing_uncertainty_fails_even_with_supported_claims() -> None:
    evidence: tuple[dict[str, object], ...] = ({"kind": "observation", "ref": "obs-1"},)
    breakdown_with_evidence = (
        _evaluation(
            "luminosidad", state="unknown", confidence=0.0, evidence_refs=evidence
        ),
    )
    reason = ExplanationReason(
        criterion_key="luminosidad",
        state="unknown",
        score=0.0,
        confidence=0.0,
        contribution=0.0,
        evidence_level="low",
        reason_code="no_observation_data",
        evidence_refs=evidence,
        text="Sin datos.",
    )
    report = evaluate_fidelity(
        explanation=_explanation(reasons=(reason,), missing_data=()),
        breakdown=breakdown_with_evidence,
    )
    assert not report.passing
    assert "luminosidad" in report.missing_uncertainty


def test_legacy_no_breakdown_item_is_excluded_and_passes() -> None:
    report = evaluate_fidelity(
        explanation=_explanation(score_version="scoring-baseline-v1"),
        breakdown=(),
    )
    assert report.passing
    assert report.no_breakdown_items
    assert report.reasons == ("legacy_no_breakdown",)
