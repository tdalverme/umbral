"""Pure deterministic hard filters over candidate listings.

Hard filters in v1 cover: operation, budget (upper bound), location (CABA
zones) and rooms. Surface bounds and budget lower bounds are scoring
dimensions, not hard filters. Unknown values follow the versioned per-filter
strategy of the search profile contract (price/location -> exclude;
rooms -> include); a known value that violates a bound is always excluded
regardless of strategy. The candidate SQL query narrows the set; this pure
policy is the source of truth applied on the results.
"""

from __future__ import annotations

from typing import Literal, Protocol

from umbral.application.radar.contracts import SearchProfile

_RESIDENTIAL_PROPERTY_TYPES = frozenset({"apartment", "house", "room", "studio"})


class CandidateListing(Protocol):
    """The minimal listing surface the filters consume."""

    @property
    def operation(self) -> Literal["rental"]: ...

    @property
    def property_type(self) -> str: ...

    @property
    def total_cost(self) -> float: ...

    @property
    def neighborhood(self) -> str | None: ...

    @property
    def rooms(self) -> int | None: ...


def apply_hard_filters(listing: CandidateListing, profile: SearchProfile) -> bool:
    """True when the listing passes every hard filter of the profile."""
    if listing.operation != profile.operation:
        return False
    if listing.property_type not in _RESIDENTIAL_PROPERTY_TYPES:
        return False

    if profile.budget_max is not None:
        if listing.total_cost is None or listing.total_cost <= 0:
            return False
        if listing.total_cost > profile.budget_max:
            return False

    if profile.zones:
        if listing.neighborhood is None:
            return False
        if listing.neighborhood.casefold() not in _zones_casefold(profile):
            return False

    if profile.min_rooms is not None and profile.min_rooms > 0:
        if listing.rooms is None:
            if _strategy(profile, "rooms") == "exclude":
                return False
        elif listing.rooms < profile.min_rooms:
            return False

    return True


def _strategy(profile: SearchProfile, filter_name: str) -> str:
    return profile.unknown_strategy.get(filter_name, "exclude")


def _zones_casefold(profile: SearchProfile) -> frozenset[str]:
    return frozenset(zone.casefold() for zone in profile.zones)
