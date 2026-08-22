from __future__ import annotations

from umbral.application.playground.contracts import GeoInspectionRequest
from umbral.infrastructure.playground.geo import build_local_geo_inspector


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
