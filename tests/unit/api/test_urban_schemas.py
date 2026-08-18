"""Urban signal response/request schema shape follows the product contract."""

from __future__ import annotations

from umbral.api.routers.urban import (
    UrbanSignalItem,
    UrbanSignalsResponse,
)


def test_signal_item_exposes_catalog_fields() -> None:
    item = UrbanSignalItem(
        name="cafe_lifestyle", kind="density", normalized_by="barrio"
    )

    assert item.name == "cafe_lifestyle"
    assert item.kind == "density"
    assert item.normalized_by == "barrio"


def test_signals_response_carries_attribution_and_license() -> None:
    response = UrbanSignalsResponse(
        contract_version="urban-contract-v1",
        attribution="© OpenStreetMap contributors",
        license="odbl-1.0",
        signals=[
            UrbanSignalItem(
                name="cafe_lifestyle", kind="density", normalized_by="barrio"
            )
        ],
    )

    assert response.attribution == "© OpenStreetMap contributors"
    assert response.license == "odbl-1.0"
    assert response.signals[0].name == "cafe_lifestyle"
    assert response.contract_version == "urban-contract-v1"
