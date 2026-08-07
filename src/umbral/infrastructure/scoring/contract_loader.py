"""Loads the published scoring contracts from the repository contracts tree."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

_POLICY_SEED_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "scoring"
    / "v1"
    / "scoring-policy-v1.json"
)
_EXPLANATIONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "scoring"
    / "v1"
    / "explanations-v1.json"
)


def load_scoring_policy_seed(path: Path | None = None) -> Mapping[str, object]:
    source = path or _POLICY_SEED_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("scoring policy seed must be an object")
    return dict(data)


def load_explanations_templates(path: Path | None = None) -> Mapping[str, str]:
    source = path or _EXPLANATIONS_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("explanations contract must be an object")
    templates = data.get("copy_templates")
    if not isinstance(templates, Mapping):
        raise ValueError("explanations contract requires copy_templates")
    return {str(key): str(value) for key, value in templates.items()}
