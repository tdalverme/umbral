"""Inspectable urban lineage over the published contract and calculator."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from umbral.application.playground.contracts import GeoInspection, GeoInspectionRequest
from umbral.application.urban.calculator import UrbanSignalCalculator
from umbral.infrastructure.playground.fixtures import (
    PlaygroundFixture,
    PlaygroundFixtures,
    load_playground_catalog,
)
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published


class LocalGeoInspector:
    def __init__(self, fixtures: PlaygroundFixtures | None = None) -> None:
        self.fixtures = fixtures or load_playground_catalog()
        self.contract = load_urban_contract_published()
        self.calculator = UrbanSignalCalculator(self.contract)

    def inspect(self, request: GeoInspectionRequest) -> GeoInspection:
        fixture = self.fixtures.by_id(request.fixture_id)
        listing = _listing_by_id(fixture, request.listing_id)
        radius_m = max(1, int(request.radius_m))
        urban = _urban_for_listing(fixture, listing_id=request.listing_id)
        features = tuple(
            serialize_feature(feature)
            for feature in _features_within_radius(urban.get("features"), radius_m)
        )
        poi_distances = _bounded_distances(urban.get("poi_distances"), radius_m)
        linear_distances = _bounded_distances(urban.get("linear_distances"), radius_m)
        calculated = self.calculator.calculate(
            poi_distances=poi_distances,
            linear_distances=linear_distances,
        )
        primitives = _primitive_rows(
            contract=self.contract,
            features=features,
            poi_distances=poi_distances,
            linear_distances=linear_distances,
        )
        signals = tuple(
            {
                "signal": name,
                "value": value.value,
                "normalized_value": value.value,
                "confidence": value.confidence,
                "missing": value.missing,
                "inputs_present": value.inputs_present,
                "inputs_total": value.inputs_total,
                "contributors": [dict(item) for item in value.contributors],
            }
            for name, value in sorted(
                calculated.signals.items(),
                key=lambda item: (item[1].missing, item[0]),
            )
        )
        return GeoInspection(
            fixture_id=request.fixture_id,
            listing_id=request.listing_id,
            radius_m=radius_m,
            listing=copy.deepcopy(dict(listing)),
            features=features,
            primitives=primitives,
            signals=signals,
            contract_version=calculated.contract_version,
            snapshot_id=str(urban.get("snapshot_id", "fixture")),
            attribution=self.contract.source.attribution,
            warnings=(),
        )


def build_local_geo_inspector(snapshot_path: Path | None = None) -> LocalGeoInspector:
    return LocalGeoInspector(load_playground_catalog(snapshot_path))


def serialize_feature(feature: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "id": str(feature.get("id", "")),
        "name": str(feature.get("name", "")),
        "category": str(feature.get("category", "")),
        "kind": str(feature.get("kind", "poi")),
        "distance_m": feature.get("distance_m"),
        "geometry": copy.deepcopy(feature.get("geometry")),
    }


def _listing_by_id(fixture: PlaygroundFixture, listing_id: str) -> Mapping[str, object]:
    for listing in fixture.listings:
        if listing_id in {str(listing.get("id")), str(listing.get("uuid"))}:
            return listing
    raise KeyError(f"unknown fixture listing: {listing_id}")


def _urban_for_listing(
    fixture: PlaygroundFixture, *, listing_id: str
) -> Mapping[str, object]:
    urban = fixture.urban
    by_listing = urban.get("by_listing")
    if not isinstance(by_listing, Mapping):
        return urban
    listing = _listing_by_id(fixture, listing_id)
    for candidate_id in (listing_id, listing.get("id"), listing.get("uuid")):
        if candidate_id is None:
            continue
        selected = by_listing.get(str(candidate_id))
        if isinstance(selected, Mapping):
            resolved = dict(selected)
            if "snapshot_id" not in resolved and "snapshot_id" in urban:
                resolved["snapshot_id"] = urban["snapshot_id"]
            return resolved
    return {}


def _features_within_radius(
    raw_features: object, radius_m: int
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(raw_features, list):
        return ()
    return tuple(
        item
        for item in raw_features
        if isinstance(item, Mapping)
        and isinstance(item.get("distance_m"), (int, float))
        and float(item["distance_m"]) <= radius_m
    )


def _bounded_distances(
    raw_distances: object, radius_m: int
) -> dict[str, dict[str, list[float]]]:
    if not isinstance(raw_distances, Mapping):
        return {}
    result: dict[str, dict[str, list[float]]] = {}
    for category, raw_metrics in raw_distances.items():
        if not isinstance(raw_metrics, Mapping):
            continue
        metrics: dict[str, list[float]] = {}
        for metric, raw_values in raw_metrics.items():
            if not isinstance(raw_values, list):
                continue
            values = [
                float(value)
                for value in raw_values
                if isinstance(value, (int, float)) and float(value) <= radius_m
            ]
            if str(metric).startswith("count_"):
                metric_radius = _metric_radius(str(metric))
                if metric_radius > radius_m:
                    values = []
            metrics[str(metric)] = values
        result[str(category)] = metrics
    return result


def _primitive_rows(
    *,
    contract: Any,
    features: tuple[Mapping[str, object], ...],
    poi_distances: Mapping[str, Mapping[str, list[float]]],
    linear_distances: Mapping[str, Mapping[str, list[float]]],
) -> tuple[dict[str, object], ...]:
    categories: list[str] = []
    for feature in features:
        category = str(feature.get("category", ""))
        if category and category not in categories:
            categories.append(category)
    rows: list[dict[str, object]] = []
    for category in categories:
        specs = contract.primitives.get(category) or contract.linear_primitives.get(
            category
        )
        if not specs:
            continue
        source = poi_distances.get(category) or linear_distances.get(category) or {}
        row: dict[str, object] = {
            "category": category,
            "kind": "linear" if category in contract.linear_primitives else "poi",
            "feature_ids": [
                str(feature.get("id"))
                for feature in features
                if feature.get("category") == category
            ],
            "count_300m": None,
            "count_600m": None,
            "nearest_m": None,
        }
        for spec in specs:
            values = list(source.get(spec.name, []))
            if spec.kind == "count":
                row[spec.name] = len(values)
            elif values:
                row[spec.name] = min(values)
        rows.append(row)
    return tuple(rows)


def _metric_radius(metric: str) -> float:
    try:
        return float(metric.removeprefix("count_").removesuffix("m"))
    except ValueError:
        return 0.0
