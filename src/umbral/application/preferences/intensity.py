"""Deterministic weights for model-declared preference intensity."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

PreferenceIntensity = Literal["low", "medium", "high", "essential"]
PreferencePolarity = Literal["positive", "negative"]

_LEVELS: tuple[PreferenceIntensity, ...] = ("low", "medium", "high", "essential")
_POLICY_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "preferences"
    / "intensity-policy-v1.json"
)


@dataclass(frozen=True, slots=True)
class IntensityPolicy:
    """Validated policy mapping ordered intensity levels to soft weights."""

    version: str
    weights: Mapping[PreferenceIntensity, float]

    def weight_for(self, level: PreferenceIntensity) -> float:
        return self.weights[level]


def load_intensity_policy(path: Path | None = None) -> IntensityPolicy:
    """Load the versioned policy and reject a non-deterministic level map."""
    source = path or _POLICY_PATH
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("intensity policy must be an object")
    if raw.get("version") != "preference-intensity-v1":
        raise ValueError("invalid intensity policy version")
    raw_weights = raw.get("weights")
    if not isinstance(raw_weights, Mapping):
        raise ValueError("intensity weights must be an object")
    if set(raw_weights) != set(_LEVELS):
        raise ValueError("intensity levels must match the published policy")

    weights: dict[PreferenceIntensity, float] = {}
    for level in _LEVELS:
        value = raw_weights[level]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("intensity weight must be numeric")
        weight = float(value)
        if not 0.0 <= weight <= 1.0:
            raise ValueError("intensity weight must be within [0, 1]")
        weights[level] = weight
    pairs = zip(_LEVELS, _LEVELS[1:])
    if any(weights[left] >= weights[right] for left, right in pairs):
        raise ValueError("intensity weights must be strictly increasing")

    return IntensityPolicy(
        version="preference-intensity-v1",
        weights=cast(Mapping[PreferenceIntensity, float], weights),
    )
