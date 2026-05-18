"""Deterministic urban signals derived from cached OSM data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

URBAN_SIGNALS_VERSION = "urban_signals_v1"

POI_CATEGORY_BY_TAG = {
    ("shop", "supermarket"): "supermarket",
    ("shop", "convenience"): "convenience",
    ("shop", "greengrocer"): "convenience",
    ("shop", "bakery"): "convenience",
    ("amenity", "pharmacy"): "pharmacy",
    ("amenity", "hospital"): "health",
    ("amenity", "clinic"): "health",
    ("amenity", "doctors"): "health",
    ("amenity", "cafe"): "cafe",
    ("amenity", "bar"): "nightlife",
    ("amenity", "pub"): "nightlife",
    ("amenity", "nightclub"): "nightlife",
    ("amenity", "restaurant"): "restaurant",
    ("amenity", "fast_food"): "restaurant",
    ("amenity", "bus_station"): "bus_station",
    ("highway", "bus_stop"): "bus_stop",
    ("railway", "station"): "train_station",
    ("railway", "halt"): "train_station",
    ("station", "subway"): "subway_station",
    ("railway", "subway_entrance"): "subway_station",
    ("leisure", "park"): "green_space",
    ("leisure", "garden"): "green_space",
    ("landuse", "grass"): "green_space",
    ("natural", "wood"): "green_space",
    ("shop", "mall"): "shopping_mall",
}

LINEAR_CATEGORY_BY_TAG = {
    ("highway", "motorway"): "highway",
    ("highway", "trunk"): "highway",
    ("highway", "primary"): "major_road",
    ("highway", "secondary"): "major_road",
    ("railway", "rail"): "railway",
    ("railway", "subway"): "subway_line",
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _distance_score(distances: list[float], *, near: float, far: float) -> float:
    if not distances:
        return 0.0
    best = min(distances)
    if best <= near:
        return 1.0
    if best >= far:
        return 0.0
    return _clamp01(1 - ((best - near) / (far - near)))


def _count_score(distances: list[float], *, radius: float, target: int) -> float:
    if target <= 0:
        return 0.0
    count = sum(1 for distance in distances if distance <= radius)
    return _clamp01(count / target)


def classify_osm_poi(tags: dict[str, Any]) -> str | None:
    """Map raw OSM tags to the reduced categories used by scoring."""

    normalized = {str(k): str(v).lower() for k, v in (tags or {}).items() if v is not None}
    if normalized.get("station") == "subway":
        return "subway_station"
    for key, value in normalized.items():
        category = POI_CATEGORY_BY_TAG.get((key, value))
        if category:
            return category
    return None


def classify_osm_linear_feature(tags: dict[str, Any]) -> str | None:
    """Map OSM way tags to linear urban categories."""

    normalized = {str(k): str(v).lower() for k, v in (tags or {}).items() if v is not None}
    for key, value in normalized.items():
        category = LINEAR_CATEGORY_BY_TAG.get((key, value))
        if category:
            return category
    return None


@dataclass(frozen=True)
class UrbanSignalResult:
    signals: dict[str, Any]
    computed_version: str = URBAN_SIGNALS_VERSION


class UrbanSignalCalculator:
    """Calculate urban signal aggregates from precomputed distances."""

    def calculate(
        self,
        *,
        poi_distances: dict[str, list[float]] | None = None,
        linear_distances: dict[str, list[float]] | None = None,
    ) -> UrbanSignalResult:
        poi = poi_distances or {}
        linear = linear_distances or {}

        daily_distances = (
            poi.get("supermarket", [])
            + poi.get("pharmacy", [])
            + poi.get("convenience", [])
            + poi.get("health", [])
        )
        transit_distances = (
            poi.get("bus_stop", [])
            + poi.get("bus_station", [])
            + poi.get("subway_station", [])
            + poi.get("train_station", [])
        )
        nightlife_distances = poi.get("nightlife", []) + poi.get("restaurant", [])
        cafe_distances = poi.get("cafe", [])
        commercial_distances = daily_distances + cafe_distances + nightlife_distances + poi.get("shopping_mall", [])
        road_distances = linear.get("major_road", []) + linear.get("highway", [])
        rail_distances = linear.get("railway", []) + linear.get("subway_line", [])

        walkability = _clamp01(
            0.45 * _count_score(daily_distances, radius=600, target=6)
            + 0.35 * _distance_score(poi.get("supermarket", []) + poi.get("pharmacy", []), near=150, far=800)
            + 0.20 * _count_score(commercial_distances, radius=800, target=16)
        )
        transit_access = _clamp01(
            0.55 * _count_score(poi.get("bus_stop", []) + poi.get("bus_station", []), radius=350, target=3)
            + 0.35 * _distance_score(poi.get("subway_station", []), near=250, far=1000)
            + 0.10 * _distance_score(poi.get("train_station", []), near=300, far=1200)
        )
        nightlife_intensity = _clamp01(
            0.65 * _count_score(nightlife_distances, radius=300, target=5)
            + 0.35 * _distance_score(poi.get("nightlife", []), near=80, far=450)
        )
        road_noise = _distance_score(road_distances, near=40, far=300)
        rail_noise = _distance_score(rail_distances, near=80, far=650)
        noise_risk = _clamp01(0.45 * nightlife_intensity + 0.35 * road_noise + 0.20 * rail_noise)
        green_access = _clamp01(
            0.70 * _distance_score(poi.get("green_space", []), near=150, far=900)
            + 0.30 * _count_score(poi.get("green_space", []), radius=1000, target=3)
        )
        cafe_lifestyle = _clamp01(
            0.65 * _count_score(cafe_distances, radius=600, target=5)
            + 0.35 * _distance_score(cafe_distances, near=100, far=650)
        )
        commercial_intensity = _clamp01(
            0.70 * _count_score(commercial_distances, radius=700, target=18)
            + 0.30 * _distance_score(poi.get("shopping_mall", []), near=250, far=1200)
        )
        daily_convenience = _clamp01(
            0.70 * _count_score(daily_distances, radius=600, target=6)
            + 0.30 * _distance_score(daily_distances, near=150, far=750)
        )
        residential_calm = _clamp01(1 - (0.70 * noise_risk + 0.30 * commercial_intensity))
        confidence = _clamp01(0.5 + 0.5 * min(1.0, len(commercial_distances + transit_distances + road_distances) / 12))

        contributors = self._contributors(poi, linear)
        return UrbanSignalResult(
            signals={
                "noise_risk": noise_risk,
                "walkability": walkability,
                "transit_access": transit_access,
                "green_access": green_access,
                "nightlife_intensity": nightlife_intensity,
                "daily_convenience": daily_convenience,
                "cafe_lifestyle": cafe_lifestyle,
                "commercial_intensity": commercial_intensity,
                "residential_calm": residential_calm,
                "confidence": confidence,
                "contributors": contributors,
            }
        )

    def neutral(self, reason: str = "missing_coordinates") -> UrbanSignalResult:
        return UrbanSignalResult(
            signals={
                "noise_risk": 0.5,
                "walkability": 0.5,
                "transit_access": 0.5,
                "green_access": 0.5,
                "nightlife_intensity": 0.5,
                "daily_convenience": 0.5,
                "cafe_lifestyle": 0.5,
                "commercial_intensity": 0.5,
                "residential_calm": 0.5,
                "confidence": 0.2,
                "contributors": [{"type": reason, "confidence": 0.2}],
            }
        )

    def _contributors(
        self,
        poi: dict[str, list[float]],
        linear: dict[str, list[float]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for category, distances in {**poi, **linear}.items():
            if not distances:
                continue
            candidates.append(
                {
                    "type": category,
                    "distance_m": round(min(distances), 1),
                    "count_300m": sum(1 for distance in distances if distance <= 300),
                    "count_600m": sum(1 for distance in distances if distance <= 600),
                }
            )
        return sorted(candidates, key=lambda item: item["distance_m"])[:8]
