"""Conformance of the product events registry and its validation."""

from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.criteria import golden as criteria_golden
from tests.fixtures.radar.golden import load_events_golden
from umbral.application.events.registry import (
    event_version,
    parse_events_registry,
    validate_event,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "contracts" / "events" / "v1" / "events-registry.json"

REGISTRY = load_events_registry(REGISTRY_PATH)


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    parsed = parse_events_registry(published)
    assert parsed.contract_version == "1"
    assert parsed.registry_version == "events-v1"
    assert "radar.created.v1" in parsed.event_types
    assert "recommendation.run_published.v1" in parsed.event_types
    assert "email" in parsed.forbidden_keys


def test_all_golden_event_cases_validate_as_declared() -> None:
    for case in load_events_golden():
        error = validate_event(REGISTRY, case["event_type"], case["payload"])
        expected = case["expected"].get("error")
        if expected is None:
            assert error is None, case["id"]
        else:
            assert error == expected, case["id"]


def test_event_version_resolves_from_the_registry() -> None:
    assert event_version(REGISTRY, "radar.created.v1") == 1
    assert event_version(REGISTRY, "does.not.exist.v1") is None


def test_unknown_type_and_extra_keys_are_rejected() -> None:
    assert validate_event(REGISTRY, "chat.sent.v1", {}) == "events.unknown_type"
    error = validate_event(
        REGISTRY,
        "recommendation.impression.v1",
        {
            "search_profile_id": "a" * 32,
            "run_id": "b" * 32,
            "listing_id": "c" * 32,
            "unexpected": 1,
        },
    )
    assert error == "events.extra_keys"


def test_criteria_event_types_are_registered() -> None:
    for event_type in (
        "criteria.concept_version_created.v1",
        "criteria.compilation_created.v1",
        "criteria.observation_batch_published.v1",
        "criteria.recompute_completed.v1",
    ):
        assert event_version(REGISTRY, event_type) == 1


def test_criteria_golden_events_validate_as_declared() -> None:
    cases = criteria_golden.events_golden()
    for case in cases["valid"]:
        assert validate_event(REGISTRY, case["event_type"], case["payload"]) is None
    for case in cases["invalid"]:
        assert validate_event(REGISTRY, case["event_type"], case["payload"]) is not None


def test_criteria_events_forbid_values_and_fragments() -> None:
    error = validate_event(
        REGISTRY,
        "criteria.recompute_completed.v1",
        {
            "recompute_run_id": "a" * 32,
            "scope_kind": "concept",
            "scope_key": "balcon",
            "cause": "causa",
            "state": "succeeded",
            "published_count": 3,
            "failed_count": 0,
            "fragment": "texto",
        },
    )
    assert error == "events.forbidden_keys"


def test_scoring_event_types_are_registered() -> None:
    for event_type in (
        "recommendation.explanation_viewed.v1",
        "recommendation.comparison_viewed.v1",
    ):
        assert event_version(REGISTRY, event_type) == 1


def test_scoring_view_events_validate_with_ids_and_counts_only() -> None:
    assert (
        validate_event(
            REGISTRY,
            "recommendation.explanation_viewed.v1",
            {
                "search_profile_id": "a" * 32,
                "run_id": "b" * 32,
                "listing_id": "c" * 32,
                "score_version": "scoring-policy-v1",
            },
        )
        is None
    )
    assert (
        validate_event(
            REGISTRY,
            "recommendation.comparison_viewed.v1",
            {
                "search_profile_id": "a" * 32,
                "run_id": "b" * 32,
                "listing_count": 3,
                "score_version": "scoring-policy-v1",
            },
        )
        is None
    )


def test_scoring_view_events_reject_evidence_and_values() -> None:
    error = validate_event(
        REGISTRY,
        "recommendation.explanation_viewed.v1",
        {
            "search_profile_id": "a" * 32,
            "run_id": "b" * 32,
            "listing_id": "c" * 32,
            "score_version": "scoring-policy-v1",
            "value": 0.7,
        },
    )
    assert error == "events.forbidden_keys"
