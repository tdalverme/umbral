"""Loads the published feedback and learning contracts from the repository tree."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

_QUICK_REASONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "feedback"
    / "v1"
    / "quick-reasons-v1.json"
)
_LEARNING_POLICY_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "learning"
    / "v1"
    / "learning-policy-v1.json"
)


def load_quick_reasons_seed(path: Path | None = None) -> Mapping[str, object]:
    source = path or _QUICK_REASONS_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("quick reasons seed must be an object")
    return dict(data)


def load_learning_policy_seed(path: Path | None = None) -> Mapping[str, object]:
    source = path or _LEARNING_POLICY_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("learning policy seed must be an object")
    return dict(data)
