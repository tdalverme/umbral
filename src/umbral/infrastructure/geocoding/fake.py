"""Deterministic test double for the Geocoder seam."""

from __future__ import annotations

from umbral.application.silver.contracts import GeoPrecision, GeoResult

# Registered-source fixture: neighborhood -> fixed CABA centroid.
_FAKE_POINTS: dict[str, tuple[float, float]] = {
    "sannicolas": (-34.6037, -58.3983),
    "palermo": (-34.5851, -58.4246),
    "caballito": (-34.6204, -58.4442),
    "montserrat": (-34.6131, -58.3857),
    "recoleta": (-34.5875, -58.3923),
}


class FakeGeocoder:
    """Returns coordinates for known neighborhoods; never raises precision."""

    source = "fake.geocoder"

    def geocode(
        self, *, location_text: str, neighborhood: str | None, max_precision: str
    ) -> GeoResult:
        del location_text
        key = (neighborhood or "").strip().casefold().replace(" ", "")
        point = _FAKE_POINTS.get(key)
        if point is None:
            return GeoResult(geometry=None, precision="unknown", source=None)
        precision: GeoPrecision = "neighborhood"
        if _order(max_precision) < _order(precision):
            precision = max_precision  # type: ignore[assignment]
        return GeoResult(geometry=point, precision=precision, source=self.source)


def _order(value: str) -> int:
    return {
        "unknown": 0,
        "approximate": 1,
        "neighborhood": 2,
        "block": 3,
        "exact": 4,
    }[value]
