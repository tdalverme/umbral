"""Composition helper for the Silver application service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from umbral.application.silver.service import NormalizeRunService
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyRawSnapshotRepository,
)
from umbral.infrastructure.db.repositories.silver import (
    SqlAlchemyCanonicalPropertyRepository,
    SqlAlchemyChangeRepository,
    SqlAlchemyDedupeLinkRepository,
    SqlAlchemySilverListingRepository,
)
from umbral.infrastructure.geocoding.fake import FakeGeocoder
from umbral.infrastructure.geocoding.nominatim import NominatimGeocoder
from umbral.infrastructure.silver.contract_loader import (
    load_dedupe_policy,
    load_silver_schema,
)

SessionFactory = Callable[[], Any]


def build_normalize_service(
    *,
    session_factory: SessionFactory,
    geocoding_enabled: bool = False,
    geocoding_endpoint: str | None = None,
    geocoding_cache_size: int = 512,
    geocoding_rate_limit: float = 1.0,
    clock: Callable[[], datetime] | None = None,
) -> NormalizeRunService:
    schema = load_silver_schema()
    dedupe = load_dedupe_policy()
    geocoder = _geocoder(
        enabled=geocoding_enabled,
        endpoint=geocoding_endpoint,
        cache_size=geocoding_cache_size,
        rate_limit=geocoding_rate_limit,
    )
    return NormalizeRunService(
        listings=SqlAlchemySilverListingRepository(session_factory),
        canonicals=SqlAlchemyCanonicalPropertyRepository(session_factory),
        links=SqlAlchemyDedupeLinkRepository(session_factory),
        changes=SqlAlchemyChangeRepository(session_factory),
        snapshots=SqlAlchemyRawSnapshotRepository(session_factory),
        runs=SqlAlchemyImportRunRepository(session_factory),
        schema=schema,
        dedupe=dedupe,
        geocoder=geocoder,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )


def _geocoder(
    *,
    enabled: bool,
    endpoint: str | None,
    cache_size: int,
    rate_limit: float,
) -> FakeGeocoder | NominatimGeocoder | None:
    if not enabled:
        return None
    if endpoint is None:
        return FakeGeocoder()
    return NominatimGeocoder(
        endpoint=endpoint,
        cache_size=cache_size,
        rate_limit=rate_limit,
    )
