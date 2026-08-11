"""Notification events registry conformance (H5)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.infrastructure.radar.contract_loader import load_events_registry

ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = ROOT / "contracts" / "events" / "v1" / "events-registry.json"

_EXPECTED = {
    "notification.decision_created.v1": [
        "decision_id",
        "search_profile_id",
        "trigger",
        "reason_code",
        "decision_state",
    ],
    "notification.delivered.v1": [
        "decision_id",
        "channel",
        "provider_message_id",
    ],
    "notification.delivery_failed.v1": ["decision_id", "channel", "error_code"],
    "notification.viewed.v1": ["decision_id"],
    "notification.acted.v1": ["decision_id", "action"],
    "notification.unsubscribed.v1": ["search_profile_id"],
}


def test_notification_events_are_registered() -> None:
    registry = load_events_registry()
    for event_type in _EXPECTED:
        assert event_type in registry.event_types, f"{event_type} missing"


def test_notification_event_required_keys() -> None:
    raw = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    event_types = raw["event_types"]
    for event_type, required in _EXPECTED.items():
        assert set(event_types[event_type]["required_keys"]) == set(required)


def test_notification_events_have_no_forbidden_keys() -> None:
    raw = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    forbidden = set(raw["forbidden_keys"])
    for event_type, required in _EXPECTED.items():
        assert not (set(required) & forbidden), event_type
