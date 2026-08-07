"""Conformance of deterministic explanation generation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from umbral.application.scoring.contracts import CriterionEvaluation
from umbral.application.scoring.explanations import build_explanation
from umbral.application.scoring.policy import parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import (
    load_explanations_templates,
    load_scoring_policy_seed,
)

GOLDEN = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "scoring"
        / "explanations-golden.json"
    ).read_text(encoding="utf-8")
)

MATCHER_TYPES = load_matcher_types()
POLICY = parse_policy_document(load_scoring_policy_seed(), MATCHER_TYPES)
TEMPLATES = load_explanations_templates()

_PROFILE_ID = uuid4()
_RUN_ID = uuid4()
_LISTING_ID = uuid4()


def _evaluation(case: Mapping[str, object]) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=_RUN_ID,
        listing_id=_LISTING_ID,
        criterion_key=str(case["criterion_key"]),
        criterion_version="policy:scoring-policy-v1",
        matcher_type="categorical",
        params={},
        input_refs=(),
        score=float(case["score"]),
        confidence=float(case["confidence"]),
        state=case["state"],  # type: ignore[arg-type]
        contribution=float(case["contribution"]),
        reason_code=str(case["reason_code"]),
        evidence_refs=tuple(dict(ref) for ref in case["evidence_refs"]),
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def test_all_golden_explanation_cases_match() -> None:
    for case in GOLDEN["cases"]:
        evaluations = tuple(_evaluation(item) for item in case["evaluations"])
        explanation = build_explanation(
            search_profile_id=_PROFILE_ID,
            run_id=_RUN_ID,
            listing_id=_LISTING_ID,
            score=0.72,
            confidence=float(case["run_confidence"]),
            evaluations=evaluations,
            policy=POLICY,
            templates=TEMPLATES,
            satisfied_filters=tuple(case["profile_filters"]),
            profile_version_id=uuid4(),
        )
        expected = case["expected"]
        assert len(explanation.reasons) == expected["reason_count"], case["id"]
        assert len(explanation.risks) == expected["risk_count"], case["id"]
        assert list(explanation.missing_data) == expected["missing_data"], case["id"]
        assert list(explanation.satisfied_filters) == expected["satisfied_filters"]
        for reason, expected_reason in zip(explanation.reasons, expected["reasons"]):
            assert reason.criterion_key == expected_reason["criterion_key"]
            assert reason.state == expected_reason["state"]
            assert reason.evidence_level == expected_reason["evidence_level"]
            assert reason.text == expected_reason["text"]
        for risk, expected_risk in zip(explanation.risks, expected["risks"]):
            assert risk.criterion_key == expected_risk["criterion_key"]
            assert risk.state == expected_risk["state"]
        assert explanation.score_version == case["score_version"]


def test_two_calls_produce_identical_copy() -> None:
    case = GOLDEN["cases"][0]
    evaluations = tuple(_evaluation(item) for item in case["evaluations"])
    kwargs = dict(
        search_profile_id=_PROFILE_ID,
        run_id=_RUN_ID,
        listing_id=_LISTING_ID,
        score=0.72,
        confidence=0.3,
        evaluations=evaluations,
        policy=POLICY,
        templates=TEMPLATES,
        satisfied_filters=("budget_max",),
        profile_version_id=uuid4(),
    )
    first = build_explanation(**kwargs)
    second = build_explanation(**kwargs)
    assert first == second


def test_every_reason_references_internal_evidence_or_declares_unknown() -> None:
    case = GOLDEN["cases"][0]
    evaluations = tuple(_evaluation(item) for item in case["evaluations"])
    explanation = build_explanation(
        search_profile_id=_PROFILE_ID,
        run_id=_RUN_ID,
        listing_id=_LISTING_ID,
        score=0.72,
        confidence=0.3,
        evaluations=evaluations,
        policy=POLICY,
        templates=TEMPLATES,
        satisfied_filters=(),
        profile_version_id=uuid4(),
    )
    for reason in explanation.reasons:
        assert reason.evidence_refs, f"reason {reason.criterion_key} lacks evidence"
    for criterion_key in explanation.missing_data:
        assert any(
            risk.criterion_key == criterion_key and risk.state == "unknown"
            for risk in explanation.risks
        )
