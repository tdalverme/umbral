"""Loaders for the radar golden fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

_FIXTURES = ROOT / "tests" / "fixtures" / "radar"


def load_profiles_golden() -> list[dict[str, Any]]:
    data = json.loads((_FIXTURES / "profiles-golden.json").read_text(encoding="utf-8"))
    return [dict(item) for item in data["cases"]]


def load_scoring_golden() -> list[dict[str, Any]]:
    data = json.loads((_FIXTURES / "scoring-golden.json").read_text(encoding="utf-8"))
    return [dict(item) for item in data["cases"]]


def load_events_golden() -> list[dict[str, Any]]:
    data = json.loads((_FIXTURES / "events-golden.json").read_text(encoding="utf-8"))
    return [dict(item) for item in data["cases"]]
