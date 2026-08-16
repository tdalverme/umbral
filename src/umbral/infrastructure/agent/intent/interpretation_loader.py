"""Loads the published v4 interpretation contract from the contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

_INTERPRETATION_CONTRACT_PATH = (
    Path(__file__).resolve().parents[5]
    / "contracts"
    / "agent"
    / "v4"
    / "interpretation-schema-v4.json"
)


def load_interpretation_schema(path: Path | None = None) -> dict[str, object]:
    source = path or _INTERPRETATION_CONTRACT_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("interpretation contract must be a JSON object")
    return dict(data)