"""Loads the published radar contracts from the repository contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.events.registry import (
    EventsRegistrySpec,
    parse_events_registry,
)
from umbral.application.radar.profile_policy import (
    SearchProfilePolicySpec,
    parse_search_profile_policy,
)
from umbral.application.radar.scoring import (
    ScoringBaselineSpec,
    parse_scoring_baseline,
)

_SEARCH_PROFILE_POLICY_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "search-profiles"
    / "v1"
    / "search-profile-policy.json"
)
_SCORING_BASELINE_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "scoring"
    / "v1"
    / "scoring-baseline.json"
)
_EVENTS_REGISTRY_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "events"
    / "v1"
    / "events-registry.json"
)


def load_search_profile_policy(path: Path | None = None) -> SearchProfilePolicySpec:
    source = path or _SEARCH_PROFILE_POLICY_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_search_profile_policy(data)


def load_scoring_baseline(path: Path | None = None) -> ScoringBaselineSpec:
    source = path or _SCORING_BASELINE_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_scoring_baseline(data)


def load_events_registry(path: Path | None = None) -> EventsRegistrySpec:
    source = path or _EVENTS_REGISTRY_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_events_registry(data)
