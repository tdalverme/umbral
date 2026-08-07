"""Conformance of the scoring policy contract and its validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from umbral.application.scoring.contracts import ScoringValidationError
from umbral.application.scoring.policy import (
    ScoringPolicyDoc,
    is_fixed_criterion,
    parse_policy_document,
)
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import load_scoring_policy_seed

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "contracts" / "scoring" / "v1" / "scoring-policy-v1.json"
GOLDEN = json.loads(
    (ROOT / "tests" / "fixtures" / "scoring" / "policy-golden.json").read_text(
        encoding="utf-8"
    )
)

MATCHER_TYPES = load_matcher_types()
SEED = load_scoring_policy_seed(POLICY_PATH)


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    parsed = parse_policy_document(published, MATCHER_TYPES)
    assert parsed.contract_version == "1"
    assert parsed.score_policy_version == "scoring-policy-v1"
    assert parsed.normalization == "weighted_sum"
    assert len(parsed.criteria) == 7
    assert parsed.tie_break == ("score", "total_cost_asc", "listing_id_asc")


def test_seed_loads_and_fixed_criteria_are_registered() -> None:
    parsed = parse_policy_document(SEED, MATCHER_TYPES)
    keys = {criterion.key for criterion in parsed.criteria}
    assert keys == {
        "presupuesto",
        "ambientes",
        "superficie",
        "ubicacion",
        "balcon",
        "luminosidad",
        "estado_general",
    }
    assert is_fixed_criterion("presupuesto")
    assert not is_fixed_criterion("balcon")


def test_invalid_documents_are_rejected_with_expected_codes() -> None:
    for case in GOLDEN["invalid"]:
        with pytest.raises(ScoringValidationError) as excinfo:
            parse_policy_document(case["policy"], MATCHER_TYPES)
        assert case["expected_code"] in excinfo.value.error_codes, case["id"]


def test_all_golden_valid_policies_parse() -> None:
    for case in GOLDEN["valid"]:
        parsed = parse_policy_document(case["policy"], MATCHER_TYPES)
        assert isinstance(parsed, ScoringPolicyDoc)


def test_identical_inputs_parse_identically() -> None:
    first = parse_policy_document(SEED, MATCHER_TYPES)
    second = parse_policy_document(SEED, MATCHER_TYPES)
    assert first.criteria == second.criteria
    assert first.bonuses == second.bonuses
    assert first.penalties == second.penalties
