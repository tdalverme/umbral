"""Transport-neutral values returned by the local playground."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
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
    listing_id: str | None = None
    radius_m: int = 600
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        has_listing = self.listing_id is not None
        has_point = self.latitude is not None or self.longitude is not None
        if has_listing == has_point:
            raise ValueError(
                "geo inspection requires either listing_id or latitude and longitude"
            )
        if has_point and (self.latitude is None or self.longitude is None):
            raise ValueError("geo point inspection requires latitude and longitude")
        if has_point:
            assert self.latitude is not None
            assert self.longitude is not None
            if not isfinite(self.latitude) or not isfinite(self.longitude):
                raise ValueError("geo point coordinates must be finite")


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
