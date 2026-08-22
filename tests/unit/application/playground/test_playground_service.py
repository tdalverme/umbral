from __future__ import annotations

from dataclasses import dataclass

from umbral.application.playground.contracts import (
    ConversationRequest,
    ConversationTrace,
    GeoInspection,
    GeoInspectionRequest,
)
from umbral.application.playground.service import PlaygroundService


@dataclass
class RecordingConversationRunner:
    requests: list[ConversationRequest]

    def run(self, request: ConversationRequest) -> ConversationTrace:
        self.requests.append(request)
        return ConversationTrace(
            fixture_id=request.fixture_id,
            run_id="run-1",
            turns=(),
            state_before={},
            state_after={},
        )


@dataclass
class RecordingGeoInspector:
    requests: list[GeoInspectionRequest]

    def inspect(self, request: GeoInspectionRequest) -> GeoInspection:
        self.requests.append(request)
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


def test_run_conversation_delegates_to_local_runner() -> None:
    request = ConversationRequest(fixture_id="demo", turns=("hola",))
    runner = RecordingConversationRunner(requests=[])
    service = PlaygroundService(
        conversation=runner, geo=RecordingGeoInspector(requests=[])
    )

    result = service.run_conversation(request)

    assert result.fixture_id == "demo"
    assert runner.requests == [request]


def test_geo_inspection_delegates_to_geo_inspector() -> None:
    request = GeoInspectionRequest(
        fixture_id="demo", listing_id="listing-1", radius_m=600
    )
    geo = RecordingGeoInspector(requests=[])
    service = PlaygroundService(
        conversation=RecordingConversationRunner(requests=[]), geo=geo
    )

    result = service.inspect_listing_geo(request)

    assert result.listing_id == "listing-1"
    assert geo.requests == [request]
