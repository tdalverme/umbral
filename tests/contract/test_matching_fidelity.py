"""Conformance of the fidelity evaluator over breakdown fixtures (H3.2 shape)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from umbral.application.matching.fidelity import evaluate_fidelity
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    EvaluationState,
    EvidenceLevel,
    Explanation,
    ExplanationReason,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "scoring" / "explanations-golden.json"


def _case_payload(case_id: str) -> dict[str, Any]:
    import json

    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return next(case for case in data["cases"] if case["id"] == case_id)


def _evaluation_from(raw: dict[str, Any]) -> CriterionEvaluation:
    evidence = tuple(dict(item) for item in raw.get("evidence_refs", []))
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=uuid4(),
        listing_id=uuid4(),
        criterion_key=str(raw["criterion_key"]),
        criterion_version="policy:scoring-policy-v1",
        matcher_type="categorical",
        params={},
        input_refs=evidence,
        score=float(raw.get("score", 1.0)),
        confidence=float(raw.get("confidence", 1.0)),
        state=cast(EvaluationState, str(raw.get("state", "match"))),
        contribution=float(raw.get("contribution", 0.1)),
        reason_code=str(raw.get("reason_code", "concept_observed")),
        evidence_refs=evidence,
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def _explanation(
    *,
    reasons: tuple[ExplanationReason, ...],
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
        risks=(),
        missing_data=missing_data,
        satisfied_filters=(),
        profile_snapshot={},
        feature_snapshot={},
    )


def test_published_explanation_golden_case_with_supported_reasons_passes() -> None:
    payload = _case_payload("match_and_unknown")
    breakdown = tuple(_evaluation_from(item) for item in payload["evaluations"])
    reasons: list[ExplanationReason] = []
    for item in payload["expected"]["reasons"]:
        reasons.append(
            ExplanationReason(
                criterion_key=str(item["criterion_key"]),
                state=cast(EvaluationState, str(item["state"])),
                score=1.0,
                confidence=1.0,
                contribution=0.1,
                evidence_level=cast(
                    EvidenceLevel, str(item.get("evidence_level", "strong"))
                ),
                reason_code="budget_within_headroom",
                evidence_refs=({"kind": "listing_field", "ref": "total_cost"},),
                text=str(item.get("text", "")),
            )
        )
    explanation = _explanation(
        reasons=tuple(reasons),
        missing_data=tuple(payload["expected"]["missing_data"]),
    )
    report = evaluate_fidelity(explanation=explanation, breakdown=breakdown)
    assert report.passing


def test_claim_with_no_evidence_ref_fails_strict_threshold() -> None:
    explanation = _explanation(
        reasons=(
            ExplanationReason(
                criterion_key="estado_general",
                state="match",
                score=1.0,
                confidence=1.0,
                contribution=0.1,
                evidence_level="strong",
                reason_code="concept_observed",
                evidence_refs=(),
                text="Sin evidencia.",
            ),
        ),
    )
    report = evaluate_fidelity(explanation=explanation, breakdown=())
    assert not report.passing
    assert report.claims[0].verdict == "unsupported"
