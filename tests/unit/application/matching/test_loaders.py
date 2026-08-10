"""Unit tests for the pure golden dataset and releases loaders."""

from __future__ import annotations

from typing import Any

import pytest

from umbral.application.matching.contracts import MatchingValidationError
from umbral.application.matching.golden import parse_golden_dataset
from umbral.application.matching.releases import parse_releases


def _dataset_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "registry_version": "golden-dataset-v1",
        "reviewed_by": "product",
        "reviewed_at": "2026-08-09",
        "baseline_score_policy_version": "scoring-policy-v1",
        "cases": [
            {
                "id": "golden-001",
                "tags": [
                    "hard_filter_violation",
                    "subjective_preference",
                    "price_boundary",
                ],
                "profile": {
                    "zones": ["palermo"],
                    "budget_max": 500000,
                    "min_rooms": 2,
                },
                "criteria": [
                    {
                        "concept_key": "presupuesto",
                        "matcher_type": "numeric_range",
                        "params": {},
                    },
                ],
                "listings": [
                    {
                        "listing_id": "listing-a",
                        "total_cost": 400000,
                        "rooms": 2,
                        "surface_m2": 60,
                        "neighborhood": "palermo",
                        "geo_precision": "neighborhood",
                    }
                ],
                "expected_ranking": ["listing-a"],
                "expected_hard_filter": {"listing-a": "pass"},
            },
            {
                "id": "golden-002",
                "tags": ["unknown", "legacy_no_breakdown"],
                "profile": {
                    "zones": ["recoleta"],
                    "budget_max": 300000,
                    "min_rooms": 1,
                },
                "criteria": [],
                "listings": [
                    {
                        "listing_id": "listing-b",
                        "total_cost": 250000,
                        "rooms": 1,
                        "surface_m2": None,
                        "neighborhood": "recoleta",
                        "geo_precision": "neighborhood",
                        "legacy": True,
                    }
                ],
                "expected_ranking": ["listing-b"],
                "expected_hard_filter": {"listing-b": "pass"},
            },
        ],
    }


def test_load_golden_dataset_parses_valid_document() -> None:
    dataset = parse_golden_dataset(_dataset_payload())
    assert dataset.registry_version == "golden-dataset-v1"
    assert dataset.baseline_score_policy_version == "scoring-policy-v1"
    assert len(dataset.cases) == 2
    assert dataset.case_by_id("golden-001") is not None
    assert dataset.case_by_id("nope") is None


def test_golden_dataset_rejects_unknown_tag() -> None:
    payload = _dataset_payload()
    payload["cases"][0]["tags"] = ["made_up_tag"]

    with pytest.raises(MatchingValidationError) as raised:
        parse_golden_dataset(payload)

    assert any("unknown_tag" in code for code in raised.value.error_codes)


def test_golden_dataset_rejects_unknown_ranking_id() -> None:
    payload = _dataset_payload()
    payload["cases"][0]["expected_ranking"] = ["missing-listing"]

    with pytest.raises(MatchingValidationError) as raised:
        parse_golden_dataset(payload)

    assert any("unknown_ranking_id" in code for code in raised.value.error_codes)


def test_golden_dataset_rejects_missing_coverage() -> None:
    payload = _dataset_payload()
    payload["cases"][0]["tags"] = ["subjective_preference"]
    payload["cases"][1]["tags"] = ["price_boundary"]

    with pytest.raises(MatchingValidationError) as raised:
        parse_golden_dataset(payload)

    assert any("missing_coverage" in code for code in raised.value.error_codes)


def test_golden_dataset_rejects_duplicate_case_ids() -> None:
    payload = _dataset_payload()
    payload["cases"][1]["id"] = "golden-001"

    with pytest.raises(MatchingValidationError) as raised:
        parse_golden_dataset(payload)

    assert any("duplicate_case" in code for code in raised.value.error_codes)


def test_releases_parse_valid_document() -> None:
    registry = parse_releases(
        {
            "contract_version": "1",
            "registry_version": "matching-releases-v1",
            "releases": [
                {
                    "id": "rel-001",
                    "artifact": "scoring.policy",
                    "artifact_version": "scoring-policy-v2",
                    "owner": "owner",
                    "justification": "pesos ajustados",
                    "affected_case_ids": ["golden-001"],
                    "date": "2026-08-09",
                }
            ],
        }
    )
    assert registry.affected_for("scoring-policy-v2") == frozenset({"golden-001"})
    assert registry.affected_for("scoring-policy-v9") == frozenset()


def test_releases_reject_unknown_artifact() -> None:
    with pytest.raises(MatchingValidationError) as raised:
        parse_releases(
            {
                "contract_version": "1",
                "registry_version": "matching-releases-v1",
                "releases": [
                    {
                        "id": "rel-001",
                        "artifact": "not.known",
                        "artifact_version": "v2",
                        "owner": "owner",
                        "justification": "x",
                        "affected_case_ids": ["golden-001"],
                        "date": "2026-08-09",
                    }
                ],
            }
        )

    assert any("unknown_artifact" in code for code in raised.value.error_codes)


def test_releases_reject_unknown_affected_case_ids_when_known() -> None:
    with pytest.raises(MatchingValidationError) as raised:
        parse_releases(
            {
                "contract_version": "1",
                "registry_version": "matching-releases-v1",
                "releases": [
                    {
                        "id": "rel-001",
                        "artifact": "scoring.policy",
                        "artifact_version": "v2",
                        "owner": "owner",
                        "justification": "x",
                        "affected_case_ids": ["does-not-exist"],
                        "date": "2026-08-09",
                    }
                ],
            },
            known_case_ids=frozenset({"golden-001"}),
        )

    assert any("unknown_affected_case" in code for code in raised.value.error_codes)
