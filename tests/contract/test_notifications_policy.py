"""Notification policy contract conformance (H5)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.notifications.policy import load_policy

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    ROOT / "contracts" / "notifications" / "v1" / "notification-policy-v1.json"
)


def test_policy_document_is_valid_json() -> None:
    raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    assert raw["registry_version"] == "notification-policy-v1"
    assert raw["contract_version"] == "1"


def test_policy_loads_with_reasonable_defaults() -> None:
    policy = load_policy(POLICY_PATH)
    assert 0.0 <= policy.immediate_score_threshold <= 1.0
    assert policy.fatigue_cooldown_hours > 0
    assert policy.fatigue_window_hours > 0
    assert 0 <= policy.digest_default_local_hour <= 23
    assert policy.digest_max_items > 0
    assert policy.quiet_hours_start.hour == 22
    assert policy.quiet_hours_end.hour == 8


def test_policy_rejects_invalid_threshold() -> None:
    from umbral.application.notifications.contracts import PlannerValidationError

    data = {
        "contract_version": "1",
        "registry_version": "notification-policy-v1",
        "immediate_score_threshold": 1.5,
        "fatigue_cooldown_hours": 6,
        "fatigue_window_hours": 24,
        "digest_default_local_hour": 9,
        "digest_max_items": 10,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
    }
    try:
        from umbral.application.notifications.policy import parse_policy

        parse_policy(data)
    except PlannerValidationError as error:
        assert "threshold_range" in error.reason
    else:
        raise AssertionError("expected PlannerValidationError")
