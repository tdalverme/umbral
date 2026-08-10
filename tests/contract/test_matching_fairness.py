"""Conformance of the forbidden-features registry, seed linkage and copy scan."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.criteria.registry import is_computable, parse_concepts_seed
from umbral.application.matching.fairness import (
    load_forbidden_features,
    scan_normative_phrases,
    validate_seed_linkage,
)
from umbral.infrastructure.scoring.contract_loader import load_explanations_templates

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PATH = ROOT / "contracts" / "matching" / "v1" / "forbidden-features-v1.json"
CONCEPTS_PATH = ROOT / "contracts" / "criteria" / "v1" / "concepts-seed-v1.json"
FAIRNESS_DOC = ROOT / "docs" / "product" / "fairness-review-v1.md"


def test_contract_document_matches_the_published_json() -> None:
    forbidden = load_forbidden_features(FORBIDDEN_PATH)
    assert forbidden.contract_version == "1"
    assert forbidden.registry_version == "forbidden-features-v1"
    assert forbidden.forbidden_concepts
    assert forbidden.forbidden_proxies
    assert forbidden.normative_phrases


def test_forbidden_concepts_are_non_computable_in_the_seed() -> None:
    forbidden = load_forbidden_features(FORBIDDEN_PATH)
    seed = parse_concepts_seed(json.loads(CONCEPTS_PATH.read_text(encoding="utf-8")))
    computable = {
        concept.key: is_computable(concept.compute_policy) for concept in seed.concepts
    }
    errors = validate_seed_linkage(forbidden, computable)
    assert errors == ()


def test_seed_validation_rejects_a_forbidden_concept_marked_computable() -> None:
    forbidden = load_forbidden_features(FORBIDDEN_PATH)
    computable = {item.concept_key: True for item in forbidden.forbidden_concepts}
    errors = validate_seed_linkage(forbidden, computable)
    assert errors
    assert all("forbidden_must_be_non_computable" in error for error in errors)


def test_normative_phrase_scan_passes_on_published_templates() -> None:
    forbidden = load_forbidden_features(FORBIDDEN_PATH)
    templates = load_explanations_templates()
    flagged = scan_normative_phrases(templates, forbidden)
    assert flagged == ()


def test_normative_phrase_scan_flags_forbidden_copy() -> None:
    forbidden = load_forbidden_features(FORBIDDEN_PATH)
    templates = {"reason.zone": "Esta es la mejor zona para vivir."}
    flagged = scan_normative_phrases(templates, forbidden)
    assert flagged == ("reason.zone",)


def test_fairness_review_document_exists() -> None:
    assert FAIRNESS_DOC.exists()
    content = FAIRNESS_DOC.read_text(encoding="utf-8")
    assert "barrio_seguro" in content
