"""Golden fixtures accessors for the criteria contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

_FIXTURES = Path(__file__).resolve().parent


def _load(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((_FIXTURES / name).read_text(encoding="utf-8")),
    )


def concepts_golden() -> dict[str, Any]:
    return _load("concepts-golden.json")


def rules_golden() -> dict[str, Any]:
    return _load("rules-golden.json")


def facts_golden() -> dict[str, Any]:
    return _load("facts-golden.json")


def compilations_golden() -> dict[str, Any]:
    return _load("compilations-golden.json")


def events_golden() -> dict[str, Any]:
    return _load("events-golden.json")
