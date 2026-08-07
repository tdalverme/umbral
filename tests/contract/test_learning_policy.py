"""Conformance of the learning policy contract (FR-009)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from umbral.application.feedback.contracts import FeedbackValidationError
from umbral.application.feedback.policy import parse_learning_policy
from umbral.infrastructure.feedback.contract_loader import load_learning_policy_seed

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "feedback" / "learning-policy-golden.json"

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_seed_loads_from_the_published_contract() -> None:
    doc = parse_learning_policy(load_learning_policy_seed())
    assert doc.contract_version == "1"
    assert doc.learning_policy_version == "learning-v1"
    assert doc.min_signals == 3
    assert doc.window_days == 90
    assert doc.cooldown_days == 7
    assert doc.proposal_expiration_days == 30


def test_golden_valid_policy_parses() -> None:
    for case in GOLDEN["valid"]:
        doc = parse_learning_policy(case["policy"])
        assert doc.min_signals == case["policy"]["min_signals"]


@pytest.mark.parametrize("case", GOLDEN["invalid"], ids=lambda item: item["id"])
def test_golden_invalid_policies_are_rejected(case: dict[str, object]) -> None:
    with pytest.raises(FeedbackValidationError) as excinfo:
        parse_learning_policy(case["policy"])  # type: ignore[arg-type]
    assert case["expected_code"] in excinfo.value.error_codes


def test_coherent_defaults_when_fields_absent() -> None:
    doc = parse_learning_policy(
        {
            "contract_version": "1",
            "learning_policy_version": "v",
            "min_signals": 2,
            "window_days": 30,
            "min_signal_confidence": 1.0,
            "cooldown_days": 5,
            "proposal_expiration_days": 14,
            "default_suggested_weight": 0.4,
            "default_suggested_confidence": 0.5,
        }
    )
    assert doc.min_signals == 2
