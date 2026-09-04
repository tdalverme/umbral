"""Contract tests for deterministic semantic preference intensity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from umbral.application.preferences.intensity import load_intensity_policy

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "contracts" / "preferences" / "intensity-policy-v1.json"


def _policy_document() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _write_policy(document: dict[str, object]) -> Path:
    path = POLICY_PATH.with_name("_test-intensity-policy.json")
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_published_intensity_policy_assigns_exact_deterministic_weights() -> None:
    """A changed level-to-weight mapping would silently change soft ranking."""
    policy = load_intensity_policy(POLICY_PATH)

    assert policy.version == "preference-intensity-v1"
    levels = ("low", "medium", "high", "essential")
    assert [policy.weight_for(level) for level in levels] == [
        0.25,
        0.50,
        0.75,
        1.00,
    ]


@pytest.mark.parametrize(
    "weights",
    [
        {"low": 0.25, "medium": 0.50, "high": 0.75},
        {"low": 0.25, "medium": 0.50, "high": 0.75, "essential": 1.00, "urgent": 1.0},
        {"low": False, "medium": 0.50, "high": 0.75, "essential": 1.00},
        {"low": 0.25, "medium": "0.50", "high": 0.75, "essential": 1.00},
        {"low": -0.01, "medium": 0.50, "high": 0.75, "essential": 1.00},
        {"low": 0.25, "medium": 0.50, "high": 0.75, "essential": 1.01},
        {"low": 0.25, "medium": 0.75, "high": 0.50, "essential": 1.00},
        {"low": 0.25, "medium": 0.50, "high": 0.50, "essential": 1.00},
    ],
)
def test_loader_rejects_invalid_level_sets_and_weights(
    weights: dict[str, object]
) -> None:
    """Incomplete, nonnumeric, out-of-range, or unordered levels are unsafe."""
    document = _policy_document()
    document["weights"] = weights

    path = _write_policy(document)
    try:
        with pytest.raises(ValueError):
            load_intensity_policy(path)
    finally:
        path.unlink()
