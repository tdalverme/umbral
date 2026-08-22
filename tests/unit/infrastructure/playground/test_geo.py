from __future__ import annotations

import json

from umbral.application.playground.contracts import GeoInspectionRequest
from umbral.infrastructure.playground.fixtures import load_playground_catalog
from umbral.infrastructure.playground.geo import (
    LocalGeoInspector,
    build_local_geo_inspector,
)


def test_geo_inspection_exposes_feature_primitive_signal_lineage() -> None:
    result = build_local_geo_inspector().inspect(
        GeoInspectionRequest(
            fixture_id="demo",
            listing_id="listing-palermo-001",
            radius_m=600,
        )
    )

    assert result.features
    assert result.primitives[0]["category"] == "cafe"
    assert any(item["signal"] == "cafe_lifestyle" for item in result.signals)
    assert result.signals[0]["contributors"]


def test_geo_inspection_keeps_unsupported_metrics_missing() -> None:
    result = build_local_geo_inspector().inspect(
        GeoInspectionRequest(
            fixture_id="demo",
            listing_id="listing-palermo-001",
            radius_m=600,
        )
    )

    subway = next(
        item for item in result.primitives if item["category"] == "subway_station"
    )
    assert subway["count_300m"] is None


def test_geo_inspection_uses_listing_specific_urban_data(tmp_path) -> None:
    snapshot = {
        "id": "real-snapshot-test",
        "profile": {"id": "profile-test"},
        "listings": [
            {"id": "listing-real-001", "neighborhood": "Belgrano"},
            {"id": "listing-real-002", "neighborhood": "Palermo"},
        ],
        "urban": {
            "snapshot_id": "urban-snapshot-test",
            "by_listing": {
                "listing-real-001": {
                    "features": [
                        {
                            "id": "poi-belgrano-cafe",
                            "name": "Café Belgrano",
                            "category": "cafe",
                            "kind": "poi",
                            "distance_m": 100,
                            "geometry": {"type": "Point", "coordinates": [0, 0]},
                        }
                    ],
                    "poi_distances": {
                        "cafe": {
                            "count_300m": [100],
                            "count_600m": [100],
                            "nearest_m": [100],
                        }
                    },
                    "linear_distances": {},
                },
                "listing-real-002": {
                    "features": [],
                    "poi_distances": {},
                    "linear_distances": {},
                },
            },
        },
    }
    path = tmp_path / "real-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    inspector = LocalGeoInspector(load_playground_catalog(path))

    result = inspector.inspect(
        GeoInspectionRequest(
            fixture_id="real-snapshot-test",
            listing_id="listing-real-001",
            radius_m=600,
        )
    )

    assert [feature["id"] for feature in result.features] == ["poi-belgrano-cafe"]
    assert result.snapshot_id == "urban-snapshot-test"
