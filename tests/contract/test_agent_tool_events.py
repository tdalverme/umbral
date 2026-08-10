"""Proposal product events conformance (DoD #4, T022)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.events.registry import parse_events_registry, validate_event

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = parse_events_registry(
    json.loads(
        (ROOT / "contracts" / "events" / "v1" / "events-registry.json").read_text(
            encoding="utf-8"
        )
    )
)


def test_update_proposed_event_is_registered() -> None:
    assert validate_event(
        REGISTRY,
        "search_profile.update_proposed.v1",
        {"proposal_id": "p", "search_profile_id": "s", "base_profile_version": 1},
    ) is None


def test_update_applied_event_is_registered() -> None:
    assert validate_event(
        REGISTRY,
        "search_profile.update_applied.v1",
        {"proposal_id": "p", "search_profile_id": "s", "profile_version": 2},
    ) is None


def test_missing_keys_rejected() -> None:
    error = validate_event(
        REGISTRY, "search_profile.update_proposed.v1", {"proposal_id": "p"}
    )
    assert error is not None


def test_unknown_event_type_rejected() -> None:
    assert validate_event(REGISTRY, "unknown.event.v1", {}) is not None
