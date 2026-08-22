from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbral.api.routers.playground import (
    configure_playground_routes,
    router,
)
from umbral.application.playground.contracts import (
    ConversationTrace,
    GeoInspection,
)


class _Playground:
    def run_conversation(self, request):
        return ConversationTrace(
            fixture_id=request.fixture_id,
            run_id="run-1",
            turns=(),
            state_before={},
            state_after={},
        )

    def inspect_listing_geo(self, request):
        return GeoInspection(
            fixture_id=request.fixture_id,
            listing_id=request.listing_id,
            radius_m=request.radius_m,
            listing={},
            features=(),
            primitives=(),
            signals=(),
            contract_version="urban-contract-v2",
            snapshot_id="snapshot-1",
            attribution="© OpenStreetMap contributors",
        )


def test_playground_routes_serialize_conversation_and_geo_results() -> None:
    app = FastAPI()
    dependencies = SimpleNamespace(playground=_Playground())
    configure_playground_routes(dependencies)
    app.include_router(router)

    client = TestClient(app)
    conversation = client.post(
        "/api/v1/playground/conversations",
        json={"fixture_id": "demo", "turns": ["hola"], "model_mode": "fake"},
    )
    geo = client.post(
        "/api/v1/playground/geo",
        json={
            "fixture_id": "demo",
            "listing_id": "listing-palermo-001",
            "radius_m": 600,
        },
    )

    assert conversation.status_code == 200
    assert conversation.json()["run_id"] == "run-1"
    assert geo.status_code == 200
    assert geo.json()["contract_version"] == "urban-contract-v2"


def test_playground_app_lists_configured_real_snapshot(monkeypatch, tmp_path) -> None:
    snapshot_path = tmp_path / "real-snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "id": "real-snapshot-test",
                "profile": {"id": "profile-test"},
                "listings": [{"id": "listing-real-001", "neighborhood": "Belgrano"}],
                "urban": {"by_listing": {"listing-real-001": {"features": []}}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PLAYGROUND_SNAPSHOT_PATH", str(snapshot_path))

    from umbral.api.playground_main import create_playground_app

    response = TestClient(create_playground_app()).get("/api/v1/playground/fixtures")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["fixtures"]] == [
        "demo",
        "real-snapshot-test",
    ]
    geo = TestClient(create_playground_app()).post(
        "/api/v1/playground/geo",
        json={
            "fixture_id": "real-snapshot-test",
            "listing_id": "listing-real-001",
            "radius_m": 600,
        },
    )

    assert geo.status_code == 200
    assert geo.json()["listing_id"] == "listing-real-001"
