"""Conformance of the quick-reasons seed contract (FR-006)."""
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from umbral.application.feedback.contracts import FeedbackValidationError
from umbral.application.feedback.reasons import parse_quick_reasons
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed
from umbral.infrastructure.feedback.contract_loader import load_quick_reasons_seed

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "feedback" / "quick-reasons-golden.json"

CONCEPTS = tuple(concept.key for concept in load_concepts_seed().concepts)
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_seed_loads_from_the_published_contract() -> None:
    spec = parse_quick_reasons(load_quick_reasons_seed(), CONCEPTS)
    assert spec.contract_version == "1"
    assert spec.registry_version == "quick-reasons-v1"
    assert "price_too_high" in spec.by_key()
    assert spec.by_key()["price_too_high"].allowed_for("dislike")
    assert not spec.by_key()["price_too_high"].allowed_for("like")


def test_golden_valid_reasons_parse() -> None:
    for case in GOLDEN["valid"]:
        spec = parse_quick_reasons(
            {"contract_version": "1", "registry_version": "x", "reasons": [case["reason"]]},
            tuple(case["concepts"]),
        )
        assert spec.reasons[0].key == case["reason"]["key"]


@pytest.mark.parametrize("case", GOLDEN["invalid"], ids=lambda item: item["id"])
def test_golden_invalid_reasons_are_rejected(case: dict[str, object]) -> None:
    with pytest.raises(FeedbackValidationError) as excinfo:
        parse_quick_reasons(
            {"contract_version": "1", "registry_version": "x", "reasons": [case["reason"]]},
            tuple(cast(list[str], case["concepts"])),
        )
    assert case["expected_code"] in excinfo.value.error_codes


def test_unknown_concept_reference_is_rejected_at_parse_time() -> None:
    with pytest.raises(FeedbackValidationError) as excinfo:
        parse_quick_reasons(
            {
                "contract_version": "1",
                "registry_version": "x",
                "reasons": [
                    {
                        "key": "ghost",
                        "label": "x",
                        "polarity": "negative",
                        "concept_key": "no_such_concept",
                        "allowed_on": ["dislike"],
                    }
                ],
            },
            CONCEPTS,
        )
    assert "quick_reasons.unknown_concept" in excinfo.value.error_codes


def test_unsupported_contract_version_is_rejected() -> None:
    with pytest.raises(FeedbackValidationError):
        parse_quick_reasons(
            {"contract_version": "2", "registry_version": "x", "reasons": []},
            CONCEPTS,
        )
