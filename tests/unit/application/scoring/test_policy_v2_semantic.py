"""Scoring policy v2: semantic block and bounded soft signal handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from umbral.application.scoring.contracts import ScoringValidationError
from umbral.application.scoring.policy import parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types

ROOT = Path(__file__).resolve().parents[4]
POLICY_PATH = ROOT / "contracts" / "scoring" / "v2" / "scoring-policy-v2.json"

MATCHER_TYPES = load_matcher_types()


def _policy_document() -> dict[str, object]:
    raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    return dict(raw)


def test_policy_v2_parses_semantic_block() -> None:
    parsed = parse_policy_document(_policy_document(), MATCHER_TYPES)

    assert parsed.contract_version == "2"
    assert parsed.semantic is not None
    assert parsed.semantic.mode == "soft"
    assert parsed.semantic.max_weight == 0.10
    assert parsed.semantic.missing_evidence_contribution == 0.0


def test_semantic_hard_mode_is_rejected() -> None:
    document = _policy_document()
    document["semantic"] = {
        "mode": "hard",
        "max_weight": 0.10,
        "missing_evidence_contribution": 0.0,
    }

    with pytest.raises(ScoringValidationError) as excinfo:
        parse_policy_document(document, MATCHER_TYPES)
    assert "policy.semantic_must_be_soft" in excinfo.value.error_codes


def test_semantic_max_weight_above_cap_is_rejected() -> None:
    document = _policy_document()
    document["semantic"] = {
        "mode": "soft",
        "max_weight": 0.11,
        "missing_evidence_contribution": 0.0,
    }

    with pytest.raises(ScoringValidationError) as excinfo:
        parse_policy_document(document, MATCHER_TYPES)
    assert "policy.semantic_max_weight_exceeded" in excinfo.value.error_codes


def test_semantic_missing_evidence_contribution_must_be_zero() -> None:
    document = _policy_document()
    document["semantic"] = {
        "mode": "soft",
        "max_weight": 0.10,
        "missing_evidence_contribution": 0.01,
    }

    with pytest.raises(ScoringValidationError) as excinfo:
        parse_policy_document(document, MATCHER_TYPES)
    assert "policy.semantic_missing_evidence_nonzero" in excinfo.value.error_codes


def test_policy_v1_remains_semantic_free_and_compatible() -> None:
    v1_path = ROOT / "contracts" / "scoring" / "v1" / "scoring-policy-v1.json"
    parsed = parse_policy_document(
        json.loads(v1_path.read_text(encoding="utf-8")), MATCHER_TYPES
    )

    assert parsed.contract_version == "1"
    assert parsed.semantic is None