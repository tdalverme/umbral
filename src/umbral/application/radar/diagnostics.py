"""Deterministic zero-match diagnostics and relaxation proposals.

When a run produces zero candidates, the radar must identify the hard filters
responsible and propose concrete relaxations WITHOUT applying them (FR-021,
SC-010). This module is pure: it counts exclusions per filter and derives
bounded, non-mutating relaxation hints from the frozen profile.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from umbral.application.radar.contracts import SearchProfile

_ABSOLUTE_BUDGET_CAP = 10_000_000


class CandidateListing(Protocol):
    """The minimal listing surface used to count per-filter exclusions."""

    @property
    def operation(self) -> str: ...

    @property
    def property_type(self) -> str: ...

    @property
    def total_cost(self) -> float | None: ...

    @property
    def neighborhood(self) -> str | None: ...

    @property
    def rooms(self) -> int | None: ...


def build_diagnostics(
    *,
    profile: SearchProfile,
    candidates: tuple[CandidateListing, ...],
    supported_neighborhoods: tuple[str, ...],
    hard_criteria: tuple[str, ...] = (),
) -> Mapping[str, object]:
    """Count exclusions per hard filter and propose non-mutating relaxations.

    Returns a JSON-safe mapping with ``exclusion_counts`` (per-filter counts),
    ``active_criteria`` (the hard filters currently declared, including
    confirmed concept-level criteria from the compilation) and
    ``relaxation_proposals`` (deterministic hints; never applied here).
    """
    counts: dict[str, int] = {
        "budget_max": 0,
        "zones": 0,
        "min_rooms": 0,
    }
    total = len(candidates)
    passed = 0
    supported = frozenset(zone.casefold() for zone in supported_neighborhoods)
    zones = frozenset(zone.casefold() for zone in profile.zones)
    for listing in candidates:
        if profile.budget_max is not None and (
            listing.total_cost is None or listing.total_cost > profile.budget_max
        ):
            counts["budget_max"] += 1
            continue
        neighborhood = listing.neighborhood.casefold() if listing.neighborhood else ""
        if not neighborhood or neighborhood not in supported:
            counts["zones"] += 1
            continue
        if profile.zones and neighborhood not in zones:
            counts["zones"] += 1
            continue
        if profile.min_rooms is not None and profile.min_rooms > 0:
            if listing.rooms is None or listing.rooms < profile.min_rooms:
                counts["min_rooms"] += 1
                continue
        passed += 1
    active = tuple(
        key
        for key in ("budget_max", "zones", "min_rooms")
        if _is_active(profile, key)
    )
    # Concept-level hard criteria (confirmed soft_to_hard from the compilation)
    # are declared as active and reported so the empty-run isn't silent
    # (FR-014, SC-008). Their exclusion count depends on observations, which
    # diagnostics cannot see; the declaration is what makes the empty state
    # explainable and auditable.
    concept_hard = tuple(
        f"criterion:{key}" for key in hard_criteria if key not in active
    )
    for key in concept_hard:
        counts[key] = 0
    proposals = _relaxation_proposals(profile, hard_criteria)
    return {
        "candidate_count": total,
        "passed_count": passed,
        "exclusion_counts": counts,
        "active_criteria": list(active) + list(concept_hard),
        "relaxation_proposals": proposals,
    }


def _is_active(profile: SearchProfile, key: str) -> bool:
    if key == "budget_max":
        return profile.budget_max is not None
    if key == "zones":
        return bool(profile.zones)
    if key == "min_rooms":
        return profile.min_rooms is not None and profile.min_rooms > 0
    return False


def _relaxation_proposals(
    profile: SearchProfile, hard_criteria: tuple[str, ...] = ()
) -> list[dict[str, object]]:
    proposals: list[dict[str, object]] = []
    if profile.budget_max is not None:
        proposals.append(
            {
                "criterion": "budget_max",
                "kind": "raise_budget",
                "suggested_value": _raised_budget(profile.budget_max),
                "reason": "budget_filter_excludes_all_candidates",
            }
        )
    if profile.zones:
        proposals.append(
            {
                "criterion": "zones",
                "kind": "widen_zones",
                "suggested_value": "all_caba",
                "reason": "zone_filter_excludes_all_candidates",
            }
        )
    if profile.min_rooms is not None and profile.min_rooms > 0:
        proposals.append(
            {
                "criterion": "min_rooms",
                "kind": "lower_rooms",
                "suggested_value": max(1, profile.min_rooms - 1),
                "reason": "rooms_filter_excludes_all_candidates",
            }
        )
    for key in hard_criteria:
        proposals.append(
            {
                "criterion": key,
                "kind": "relax_criterion",
                "suggested_value": "soft",
                "reason": "concept_hard_excludes_all_candidates",
            }
        )
    return proposals


def _raised_budget(current: float) -> float:
    candidate = current * 1.25
    if candidate >= _ABSOLUTE_BUDGET_CAP:
        return float(_ABSOLUTE_BUDGET_CAP)
    return round(candidate, 2)