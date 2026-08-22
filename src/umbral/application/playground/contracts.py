"""Transport-neutral values returned by the local playground."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ModelMode = Literal["fake", "real"]


@dataclass(frozen=True, slots=True)
class ConversationRequest:
    fixture_id: str
    turns: tuple[str, ...]
    model_mode: ModelMode = "fake"


@dataclass(frozen=True, slots=True)
class ConversationTrace:
    fixture_id: str
    run_id: str
    turns: tuple[dict[str, object], ...]
    state_before: dict[str, object]
    state_after: dict[str, object]
    events: tuple[dict[str, object], ...] = field(default_factory=tuple)
    assertions: tuple[dict[str, object], ...] = field(default_factory=tuple)
    error: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class GeoInspectionRequest:
    fixture_id: str
    listing_id: str
    radius_m: int = 600


@dataclass(frozen=True, slots=True)
class GeoInspection:
    fixture_id: str
    listing_id: str
    radius_m: int
    listing: dict[str, object]
    features: tuple[dict[str, object], ...]
    primitives: tuple[dict[str, object], ...]
    signals: tuple[dict[str, object], ...]
    contract_version: str
    snapshot_id: str
    attribution: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
