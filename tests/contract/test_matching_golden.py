"""Conformance of the published golden dataset contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from umbral.application.criteria.contracts import MatcherType
from umbral.application.matching.golden import load_golden_dataset
from umbral.infrastructure.criteria.contract_loader import load_matcher_types

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "matching" / "v1" / "golden-dataset-v1.json"
SCHEMA_PATH = ROOT / "contracts" / "matching" / "v1" / "golden-dataset.schema.json"

_REQUIRED_TAGS = frozenset(
    {
        "hard_filter_violation",
        "unknown",
        "subjective_preference",
        "price_boundary",
        "legacy_no_breakdown",
    }
)


def test_contract_document_matches_the_published_json() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    assert dataset.contract_version == "1"
    assert dataset.registry_version == "golden-dataset-v1"
    assert dataset.reviewed_by
    assert dataset.reviewed_at
    assert dataset.baseline_score_policy_version
    assert len(dataset.cases) >= 5


def test_schema_document_is_valid_json() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$id"].endswith("golden-dataset.schema.json")
    assert schema["type"] == "object"
    assert "cases" in schema["properties"]


def test_dataset_covers_all_required_tag_categories() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    covered = {tag for case in dataset.cases for tag in case.tags}
    assert _REQUIRED_TAGS <= covered


def test_every_ranking_id_exists_in_listings_and_filters_are_well_formed() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    for case in dataset.cases:
        listing_ids = {listing.listing_id for listing in case.listings}
        assert len(listing_ids) == len(case.listings)
        assert len(case.expected_ranking) == len(set(case.expected_ranking))
        assert set(case.expected_ranking) <= listing_ids
        for listing_id, outcome in case.expected_hard_filter.items():
            assert listing_id in listing_ids, (case.id, listing_id)
            assert outcome in {
                "pass",
                "excluded_budget",
                "excluded_zone",
                "excluded_rooms",
            }


def test_every_case_profile_and_criteria_are_valid() -> None:
    matcher_types = load_matcher_types()
    dataset = load_golden_dataset(GOLDEN_PATH)
    for case in dataset.cases:
        assert case.profile.budget_max > 0
        assert case.profile.zones
        assert case.profile.min_rooms >= 0
        for criterion in case.criteria:
            spec = matcher_types.matcher_types.get(
                cast(MatcherType, criterion.matcher_type)
            )
            assert spec is not None, (case.id, criterion.matcher_type)
            invalid = [
                key for key in criterion.params if key not in spec.allowed_params
            ]
            assert not invalid, (case.id, criterion.concept_key, invalid)
