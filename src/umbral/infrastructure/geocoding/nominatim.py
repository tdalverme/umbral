"""Opt-in Nominatim (OpenStreetMap) geocoding adapter.

Registered source id ``osm.nominatim``. The adapter enforces a token-bucket
rate limit, an in-process LRU cache and a precision cap: the assigned precision
never exceeds ``max_precision`` supplied by the caller. Failures and
rate-limits degrade to ``unknown`` without raising, so a geocoder outage never
blocks normalization.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock

import httpx

from umbral.application.silver.contracts import GeoPrecision, GeoResult

_PRECISION_ORDER = {
    "unknown": 0,
    "approximate": 1,
    "neighborhood": 2,
    "block": 3,
    "exact": 4,
}


class _TokenBucket:
    def __init__(self, rate: float, burst: float) -> None:
        if rate <= 0:
            raise ValueError("geocoding rate must be positive")
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.updated = datetime.now(timezone.utc)

    def acquire(self, now: datetime) -> bool:
        elapsed = max(0.0, (now - self.updated).total_seconds())
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class NominatimGeocoder:
    source = "osm.nominatim"

    def __init__(
        self,
        *,
        endpoint: str,
        cache_size: int = 512,
        rate_limit: float = 1.0,
        burst: float | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        if cache_size <= 0:
            raise ValueError("geocoding cache_size must be positive")
        self._cache: OrderedDict[str, GeoResult] = OrderedDict()
        self._cache_size = cache_size
        self._bucket = _TokenBucket(rate_limit, burst or max(1.0, rate_limit))
        self._timeout = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._lock = Lock()

    def geocode(
        self, *, location_text: str, neighborhood: str | None, max_precision: str
    ) -> GeoResult:
        query = (location_text or neighborhood or "").strip()
        if not query:
            return GeoResult(geometry=None, precision="unknown", source=None)
        now = datetime.now(timezone.utc)
        with self._lock:
            if not self._bucket.acquire(now):
                return GeoResult(geometry=None, precision="unknown", source=None)
            key = " ".join(query.casefold().split())
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
        result = self._lookup(query, max_precision)
        if result.geometry is None:
            return result
        with self._lock:
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    def _lookup(self, query: str, max_precision: str) -> GeoResult:
        try:
            response = self._client.get(
                f"{self.endpoint}/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "countrycodes": "ar",
                    "accept-language": "es",
                },
            )
            response.raise_for_status()
            results = response.json()
            if not isinstance(results, list) or not results:
                return GeoResult(geometry=None, precision="unknown", source=None)
            first = results[0]
            lat = _float_field(first, "lat")
            lon = _float_field(first, "lon")
            if lat is None or lon is None:
                return GeoResult(geometry=None, precision="unknown", source=None)
        except (httpx.HTTPError, ValueError):
            return GeoResult(geometry=None, precision="unknown", source=None)
        precision: GeoPrecision = "neighborhood"
        if _order(max_precision) > _order("neighborhood"):
            precision = "block"
        return GeoResult(
            geometry=(lat, lon),
            precision=precision,
            source=self.source,
        )


def _float_field(payload: object, name: str) -> float | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _order(value: str) -> int:
    return _PRECISION_ORDER.get(value, 0)
