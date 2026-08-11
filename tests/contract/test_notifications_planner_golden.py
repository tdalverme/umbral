"""Planner golden dataset contract conformance and gate (H5)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.notifications.planner import golden_verdict
from umbral.application.notifications.planner_golden import load_golden_dataset

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "notifications" / "v1" / "planner-golden-v1.json"


def test_golden_document_is_valid_json() -> None:
    raw = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert raw["registry_version"] == "planner-golden-v1"
    assert isinstance(raw["cases"], list)


def test_golden_cases_cover_every_family() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    families = {case.family for case in dataset.cases}
    assert {
        "new_match_immediate",
        "new_match_digest",
        "price_drop",
        "duplicate",
        "quiet_hours",
        "fatigue",
    } <= families


def test_planner_golden_gate_is_green() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    for case in dataset.cases:
        ok, reason = golden_verdict(case)
        assert ok, f"{case.id}: {reason}"


def test_golden_review_is_registered() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    assert dataset.reviewed_by
    assert dataset.reviewed_at
