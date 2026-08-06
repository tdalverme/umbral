"""Geocoding adapters: precision guard, cache and rate limits."""

from __future__ import annotations

import httpx

from umbral.infrastructure.geocoding.fake import FakeGeocoder
from umbral.infrastructure.geocoding.nominatim import NominatimGeocoder


def _client_for(payload: object, *, counter: list[int] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(1)
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=1.0)


def test_fake_geocoder_resolves_known_neighborhood() -> None:
    geocoder = FakeGeocoder()
    result = geocoder.geocode(
        location_text="", neighborhood="San Nicolas", max_precision="neighborhood"
    )
    assert result.geometry is not None
    assert result.precision == "neighborhood"
    assert result.source == "fake.geocoder"


def test_fake_geocoder_never_raises_precision_above_cap() -> None:
    geocoder = FakeGeocoder()
    result = geocoder.geocode(
        location_text="", neighborhood="San Nicolas", max_precision="neighborhood"
    )
    assert result.precision == "neighborhood"


def test_fake_geocoder_unknown_neighborhood_degrades() -> None:
    geocoder = FakeGeocoder()
    result = geocoder.geocode(
        location_text="", neighborhood="Ningun Lado", max_precision="block"
    )
    assert result.geometry is None
    assert result.precision == "unknown"


def test_nominatim_parses_result_within_precision_cap() -> None:
    client = _client_for([{"lat": "-34.6037", "lon": "-58.3983"}])
    geocoder = NominatimGeocoder(endpoint="https://nominatim.example", client=client)
    result = geocoder.geocode(
        location_text="Av. Corrientes 2400", neighborhood=None, max_precision="block"
    )
    assert result.geometry == (-34.6037, -58.3983)
    assert result.precision == "block"
    assert result.source == "osm.nominatim"


def test_nominatim_neighborhood_cap_is_neighborhood() -> None:
    client = _client_for([{"lat": "-34.6037", "lon": "-58.3983"}])
    geocoder = NominatimGeocoder(endpoint="https://nominatim.example", client=client)
    result = geocoder.geocode(
        location_text="", neighborhood="San Nicolas", max_precision="neighborhood"
    )
    assert result.precision == "neighborhood"


def test_nominatim_empty_result_degrades_to_unknown() -> None:
    client = _client_for([])
    geocoder = NominatimGeocoder(endpoint="https://nominatim.example", client=client)
    result = geocoder.geocode(
        location_text="sin datos", neighborhood=None, max_precision="block"
    )
    assert result.geometry is None
    assert result.precision == "unknown"


def test_nominatim_rate_limit_degrades_without_calls() -> None:
    calls: list[int] = []
    client = _client_for([{"lat": "-34.6037", "lon": "-58.3983"}], counter=calls)
    geocoder = NominatimGeocoder(
        endpoint="https://nominatim.example",
        client=client,
        rate_limit=0.01,
        burst=1.0,
    )
    first = geocoder.geocode(
        location_text="Av. Corrientes 2400", neighborhood=None, max_precision="block"
    )
    second = geocoder.geocode(
        location_text="Av. Corrientes 2401", neighborhood=None, max_precision="block"
    )
    assert first.geometry is not None
    assert second.geometry is None
    assert second.precision == "unknown"
    assert len(calls) == 1


def test_nominatim_cache_avoids_repeat_http_calls() -> None:
    calls: list[int] = []
    client = _client_for([{"lat": "-34.6037", "lon": "-58.3983"}], counter=calls)
    geocoder = NominatimGeocoder(endpoint="https://nominatim.example", client=client)
    geocoder.geocode(
        location_text="Av. Corrientes 2400", neighborhood=None, max_precision="block"
    )
    geocoder.geocode(
        location_text="Av. Corrientes 2400", neighborhood=None, max_precision="block"
    )
    assert len(calls) == 1
