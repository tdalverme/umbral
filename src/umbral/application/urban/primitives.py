"""Pure derivation of persisted urban primitives from distance buckets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from umbral.application.urban.contract import UrbanContract

POI = "poi"
LINEAR = "linear"


def buckets_to_primitives(
    *,
    listing_id: UUID,
    snapshot_id: UUID,
    buckets: Mapping[str, Mapping[str, Sequence[float]]],
    contract: UrbanContract,
) -> tuple[Mapping[str, object], ...]:
    """Derive aggregated primitive rows from per-category distance lists.

    For each category present in the contract (poi or linear), a single row
    captures the counts within 300m/600m (when that metric is declared) and the
    nearest feature distance in metres. Categories without data are omitted.
    """
    rows: list[Mapping[str, object]] = []
    for category in contract.primitive_names():
        distances = _distance_list(buckets, category)
        spec = contract.primitives.get(category)
        if spec is None:
            spec = contract.linear_primitives.get(category)
        kind = POI if category in contract.primitives else LINEAR
        if spec is None or not distances:
            continue
        nearest = min(distances)
        row: dict[str, object] = {
            "listing_id": listing_id,
            "snapshot_id": snapshot_id,
            "category": category,
            "kind": kind,
            "count_300m": 0,
            "count_600m": 0,
            "nearest_m": float(nearest),
        }
        for metric in spec:
            if metric.name == "count_300m":
                row["count_300m"] = _count_within(distances, 300)
            elif metric.name == "count_600m":
                row["count_600m"] = _count_within(distances, 600)
        rows.append(row)
    return tuple(rows)


def _distance_list(
    buckets: Mapping[str, Mapping[str, Sequence[float]]], category: str
) -> list[float]:
    values = buckets.get(category, {})
    for distances in values.values():
        if distances:
            return [float(distance) for distance in distances]
    return []


def _count_within(distances: Sequence[float], radius_m: int) -> int:
    return sum(1 for distance in distances if distance <= radius_m)
