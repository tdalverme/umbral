"""Inspectable urban lineage over the published contract and calculator."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from math import asin, cos, hypot, radians, sin, sqrt
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
        radius_m = max(1, int(request.radius_m))
        if request.listing_id is not None:
            listing = _listing_by_id(fixture, request.listing_id)
            urban = _urban_for_listing(fixture, listing_id=request.listing_id)
            features = tuple(
                serialize_feature(feature)
                for feature in _features_within_radius(urban.get("features"), radius_m)
            )
            poi_distances = _bounded_distances(urban.get("poi_distances"), radius_m)
            linear_distances = _bounded_distances(
                urban.get("linear_distances"), radius_m
            )
            listing_id = request.listing_id
            warnings: tuple[str, ...] = ()
        else:
            assert request.latitude is not None
            assert request.longitude is not None
            urban = fixture.urban
            features = tuple(
                serialize_feature(feature)
                for feature in _features_for_point(
                    _feature_catalog(urban),
                    latitude=request.latitude,
                    longitude=request.longitude,
                    radius_m=radius_m,
                )
            )
            poi_distances, linear_distances = self._distances_for_features(features)
            listing_id = _point_id(request.latitude, request.longitude)
            listing = {
                "id": listing_id,
                "latitude": request.latitude,
                "longitude": request.longitude,
                "selection": "map_point",
            }
            warnings = (
                ("No se encontraron features dentro del radio para este punto.",)
                if not features
                else ()
            )
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
            listing_id=listing_id,
            radius_m=radius_m,
            listing=copy.deepcopy(dict(listing)),
            features=features,
            primitives=primitives,
            signals=signals,
            contract_version=calculated.contract_version,
            snapshot_id=str(urban.get("snapshot_id", "fixture")),
            attribution=self.contract.source.attribution,
            warnings=warnings,
        )

    def _distances_for_features(
        self, features: tuple[Mapping[str, object], ...]
    ) -> tuple[dict[str, dict[str, list[float]]], dict[str, dict[str, list[float]]]]:
        buckets: dict[str, dict[str, dict[str, list[float]]]] = {
            "poi": {},
            "linear": {},
        }
        for feature in features:
            category = str(feature.get("category", ""))
            kind = "linear" if feature.get("kind") == "linear" else "poi"
            specs = self.contract.linear_primitives.get(category)
            if kind == "poi":
                specs = self.contract.primitives.get(category)
            distance = feature.get("distance_m")
            if not category or not specs or not isinstance(distance, (int, float)):
                continue
            metrics = buckets[kind].setdefault(category, {})
            for spec in specs:
                metrics.setdefault(spec.name, []).append(float(distance))
        return buckets["poi"], buckets["linear"]


def build_local_geo_inspector(snapshot_path: Path | None = None) -> LocalGeoInspector:
    return LocalGeoInspector(load_playground_catalog(snapshot_path))


def serialize_feature(feature: Mapping[str, object]) -> dict[str, object]:
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


def _feature_catalog(urban: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    sources: list[object] = [urban.get("features")]
    by_listing = urban.get("by_listing")
    if isinstance(by_listing, Mapping):
        sources.extend(
            item.get("features")
            for item in by_listing.values()
            if isinstance(item, Mapping)
        )
    catalog: dict[str, Mapping[str, object]] = {}
    for raw_features in sources:
        if not isinstance(raw_features, list):
            continue
        for feature in raw_features:
            if not isinstance(feature, Mapping):
                continue
            feature_id = str(feature.get("id", ""))
            if feature_id and feature_id not in catalog:
                catalog[feature_id] = feature
    return tuple(catalog.values())


def _features_for_point(
    features: tuple[Mapping[str, object], ...],
    *,
    latitude: float,
    longitude: float,
    radius_m: int,
) -> tuple[Mapping[str, object], ...]:
    selected: list[Mapping[str, object]] = []
    for feature in features:
        distance = _distance_to_geometry(
            longitude=longitude,
            latitude=latitude,
            geometry=feature.get("geometry"),
        )
        if distance is None or distance > radius_m:
            continue
        resolved = dict(feature)
        resolved["distance_m"] = round(distance, 3)
        selected.append(resolved)
    return tuple(selected)


def _distance_to_geometry(
    *, longitude: float, latitude: float, geometry: object
) -> float | None:
    if not isinstance(geometry, Mapping):
        return None
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Point":
        point = _coordinate(coordinates)
        return (
            None
            if point is None
            else _distance_to_point(longitude, latitude, *point)
        )
    if geometry_type == "LineString" and isinstance(coordinates, list):
        points = [
            point for item in coordinates if (point := _coordinate(item)) is not None
        ]
        if not points:
            return None
        if len(points) == 1:
            return _distance_to_point(longitude, latitude, *points[0])
        return min(
            _distance_to_segment(longitude, latitude, start, end)
            for start, end in zip(points, points[1:])
        )
    return None


def _coordinate(value: object) -> tuple[float, float] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    longitude, latitude = value[:2]
    if not isinstance(longitude, (int, float)) or not isinstance(
        latitude, (int, float)
    ):
        return None
    return float(longitude), float(latitude)


def _distance_to_point(
    longitude: float, latitude: float, target_longitude: float, target_latitude: float
) -> float:
    earth_radius_m = 6_371_008.8
    lat1 = radians(latitude)
    lat2 = radians(target_latitude)
    delta_lat = lat2 - lat1
    delta_longitude = radians(target_longitude - longitude)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_longitude / 2) ** 2
    )
    return 2 * earth_radius_m * asin(sqrt(haversine))


def _distance_to_segment(
    longitude: float,
    latitude: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    earth_radius_m = 6_371_008.8
    scale = cos(radians(latitude))
    start_x = radians(start[0] - longitude) * earth_radius_m * scale
    start_y = radians(start[1] - latitude) * earth_radius_m
    end_x = radians(end[0] - longitude) * earth_radius_m * scale
    end_y = radians(end[1] - latitude) * earth_radius_m
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    denominator = delta_x * delta_x + delta_y * delta_y
    if denominator == 0:
        return hypot(start_x, start_y)
    position = max(
        0.0, min(1.0, -(start_x * delta_x + start_y * delta_y) / denominator)
    )
    return hypot(start_x + position * delta_x, start_y + position * delta_y)


def _point_id(latitude: float, longitude: float) -> str:
    return f"point:{latitude:.6f},{longitude:.6f}"


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
