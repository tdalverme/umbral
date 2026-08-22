from __future__ import annotations

import json

from umbral.infrastructure.playground.fixtures import (
    load_fixtures,
    load_playground_catalog,
)


def test_demo_fixture_contains_profile_listing_and_urban_data() -> None:
    demo = load_fixtures().by_id("demo")

    assert demo.profile["budget_max"] == 1200
    assert demo.listings[0]["id"] == "listing-palermo-001"
    assert demo.urban["features"]


def test_playground_catalog_keeps_demo_and_adds_real_snapshot(tmp_path) -> None:
    snapshot = {
        "id": "real-snapshot-test",
        "profile": {"id": "profile-test", "name": "Snapshot test"},
        "listings": [{"id": "listing-real-001", "neighborhood": "Belgrano"}],
        "urban": {"by_listing": {"listing-real-001": {"features": []}}},
    }
    path = tmp_path / "real-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")

    catalog = load_playground_catalog(path)

    assert [item.fixture_id for item in catalog.items] == ["demo", "real-snapshot-test"]
    assert catalog.by_id("real-snapshot-test").listings[0]["id"] == "listing-real-001"
