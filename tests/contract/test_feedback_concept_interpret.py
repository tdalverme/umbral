# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
# ruff: noqa: E501
"""Conformance of the concept-feedback interpretation contract (ADR 0003)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.feedback import FeedbackTestContext
from umbral.application.feedback.concept_feedback import (
    parse_concept_feedback_contract,
    validate_concept_feedback,
)
from umbral.application.feedback.contracts import FeedbackValidationError
from umbral.infrastructure.feedback.contract_loader import (
    load_concept_feedback_contract,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT / "contracts" / "feedback" / "v1" / "feedback-concept-interpret-v1.json"
)


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    spec = parse_concept_feedback_contract(published)
    assert spec.contract_version == "1"
    assert spec.schema_version == "feedback-concept-interpret-v1"
    assert spec.max_items == 5


def test_load_concept_feedback_contract_roundtrips() -> None:
    spec = parse_concept_feedback_contract(load_concept_feedback_contract())
    assert spec.schema_version == "feedback-concept-interpret-v1"


def test_validate_accepts_computable_catalog_concepts() -> None:
    ctx = FeedbackTestContext()
    items = (
        {
            "concept_key": "tipo_cocina",
            "polarity": "negative",
            "strength": "strong",
            "confidence": 0.8,
        },
    )
    validated = validate_concept_feedback(items, ctx.concepts)
    assert len(validated) == 1
    assert validated[0].concept_key == "tipo_cocina"
    assert validated[0].polarity == "negative"
    assert validated[0].strength == "strong"
    assert validated[0].confidence == 0.8


def test_validate_rejects_unknown_or_non_computable_concepts() -> None:
    ctx = FeedbackTestContext()
    ctx.concepts.computable = {"tipo_cocina"}
    with pytest.raises(FeedbackValidationError) as exc:
        validate_concept_feedback(
            ({"concept_key": "inventado", "polarity": "negative", "strength": "low", "confidence": 0.5},),
            ctx.concepts,
        )
    assert exc.value.error_codes[0] == "feedback.unknown_concept:inventado"
    with pytest.raises(FeedbackValidationError) as exc:
        validate_concept_feedback(
            ({"concept_key": "barrio_seguro", "polarity": "negative", "strength": "low", "confidence": 0.5},),
            ctx.concepts,
        )
    assert exc.value.error_codes[0] == "feedback.unknown_concept:barrio_seguro"


@pytest.mark.parametrize(
    "item",
    [
        {"concept_key": "balcon", "polarity": "neutral", "strength": "low", "confidence": 0.5},
        {"concept_key": "balcon", "polarity": "negative", "strength": "extreme", "confidence": 0.5},
        {"concept_key": "balcon", "polarity": "negative", "strength": "low", "confidence": 1.5},
        {"concept_key": "balcon", "polarity": "negative", "strength": "low", "confidence": "alta"},
        {"concept_key": "", "polarity": "negative", "strength": "low", "confidence": 0.5},
        {"polarity": "negative", "strength": "low", "confidence": 0.5},
        "no es un objeto",
    ],
)
def test_validate_rejects_malformed_items(item: object) -> None:
    ctx = FeedbackTestContext()
    with pytest.raises(FeedbackValidationError):
        validate_concept_feedback((item,), ctx.concepts)


def test_validate_limits_items_and_dedupes_concepts() -> None:
    ctx = FeedbackTestContext()
    items = tuple(
        {
            "concept_key": f"concepto_{index}",
            "polarity": "negative",
            "strength": "low",
            "confidence": 0.5,
        }
        for index in range(10)
    )
    with pytest.raises(FeedbackValidationError):
        validate_concept_feedback(items, ctx.concepts, max_items=5)