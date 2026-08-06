"""Conformance of the product events registry and its validation."""

from __future__ import annotations

import json
from pathlib import Path

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
