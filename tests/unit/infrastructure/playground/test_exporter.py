from __future__ import annotations

from umbral.infrastructure.playground.exporter import build_snapshot_payload


def test_snapshot_payload_groups_real_features_by_listing_and_kind() -> None:
    payload = build_snapshot_payload(
        listings=[
            {
                "listing_id": "listing-1",
                "source_id": "zonaprop",
                "external_id": "123",
                "neighborhood": "Belgrano",
                "latitude": -34.56,
                "longitude": -58.45,
                "total_cost": 1300,
                "price_value": 1200,
                "price_currency": "USD",
                "expenses_value": 100,
                "surface_m2": 60,
                "rooms": 3,
                "bedrooms": 2,
                "floor": 5,
                "property_type": "apartment",
                "amenities": ["balcony"],
                "url": "https://example.test/123",
            }
        ],
        features=[
            {
                "listing_id": "listing-1",
                "osm_id": "node/1",
                "category": "cafe",
                "kind": "poi",
                "name": "Cafe real",
                "distance_m": 120,
                "geometry": '{"type":"Point","coordinates":[-58.44,-34.56]}',
            },
            {
                "listing_id": "listing-1",
                "osm_id": "way/2",
                "category": "major_road",
                "kind": "linear",
                "name": "Avenida real",
                "distance_m": 340,
                "geometry": {"type": "LineString", "coordinates": []},
            },
        ],
        urban_snapshot_id="snapshot-1",
        contract_version="urban-contract-v2",
    )

    assert payload["id"] == "real-snapshot-snapshot-1"
    assert payload["listings"][0]["id"] == "listing-1"
    urban = payload["urban"]["by_listing"]["listing-1"]
    assert urban["features"][0]["geometry"]["type"] == "Point"
    assert urban["poi_distances"]["cafe"]["count_300m"] == [120.0]
    assert urban["linear_distances"]["major_road"]["nearest_m"] == [340.0]


def test_snapshot_payload_does_not_drop_listings_without_nearby_features() -> None:
    payload = build_snapshot_payload(
        listings=[{"listing_id": "listing-1", "neighborhood": "Núñez"}],
        features=[],
        urban_snapshot_id="snapshot-1",
        contract_version="urban-contract-v2",
    )

    assert list(payload["urban"]["by_listing"]) == ["listing-1"]
    assert payload["urban"]["by_listing"]["listing-1"]["features"] == []
