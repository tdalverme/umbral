"""Small, deterministic fixtures used by the local playground."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PlaygroundFixture:
    fixture_id: str
    profile: Mapping[str, object]
    listings: tuple[Mapping[str, object], ...]
    urban: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PlaygroundFixtures:
    items: tuple[PlaygroundFixture, ...]

    def by_id(self, fixture_id: str) -> PlaygroundFixture:
        for item in self.items:
            if item.fixture_id == fixture_id:
                return item
        raise KeyError(f"unknown playground fixture: {fixture_id}")


_FIXTURE_PATH = Path(__file__).with_name("fixtures") / "demo.json"


def load_fixtures(path: Path | None = None) -> PlaygroundFixtures:
    source = path or _FIXTURE_PATH
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("playground fixtures must be an object")
    fixture_id = raw.get("id")
    profile = raw.get("profile")
    listings = raw.get("listings")
    urban = raw.get("urban")
    if (
        not isinstance(fixture_id, str)
        or not isinstance(profile, Mapping)
        or not isinstance(listings, list)
        or not isinstance(urban, Mapping)
    ):
        raise ValueError("playground fixture is missing required sections")
    if not listings or not all(isinstance(item, Mapping) for item in listings):
        raise ValueError("playground fixture must contain listings")
    fixture = PlaygroundFixture(
        fixture_id=fixture_id,
        profile=copy.deepcopy(dict(profile)),
        listings=tuple(copy.deepcopy(dict(item)) for item in listings),
        urban=copy.deepcopy(dict(urban)),
    )
    return PlaygroundFixtures(items=(fixture,))
