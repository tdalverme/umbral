"""Shared builder for radar service unit tests with in-memory adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.fakes.radar import (
    FakeCandidateListingReader,
    FakeEventRepository,
    FakeItemRepository,
    FakeListingReader,
    FakeProfileVersionRepository,
    FakeRunRepository,
    FakeSearchProfileRepository,
)
from umbral.application.events.contracts import ProductEvent
from umbral.application.jobs.ports import JobRuntime
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.radar.contracts import (
    ProfileVersion,
    RecommendationItem,
    SearchProfile,
    SearchProfileState,
)
from umbral.application.radar.service import RadarService
from umbral.application.silver.contracts import (
    GeoPrecision,
    NormalizedListing,
    OperationType,
    PropertyType,
)
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.radar.contract_loader import (
    load_events_registry,
    load_scoring_baseline,
    load_search_profile_policy,
)


class _DefaultRuntime:
    pass


_DEFAULT_RUNTIME = _DefaultRuntime()


class RadarTestContext:
    def __init__(
        self, job_runtime: JobRuntime | None = None, default_runtime: bool = True
    ) -> None:
        shared_versions: dict[UUID, ProfileVersion] = {}
        shared_events: list[ProductEvent] = []
        self.profiles = FakeSearchProfileRepository(
            version_rows=shared_versions,
            event_rows=shared_events,
        )
        self.versions = FakeProfileVersionRepository(rows=shared_versions)
        shared_items: dict[UUID, list[RecommendationItem]] = {}
        self.runs = FakeRunRepository(items_by_run=shared_items)
        self.items = FakeItemRepository(items_by_run=shared_items)
        self.events = FakeEventRepository(events=shared_events)
        self.candidates = FakeCandidateListingReader()
        self.listings = FakeListingReader()
        runtime = job_runtime
        if default_runtime:
            runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
        self.service = RadarService(
            profiles=self.profiles,
            versions=self.versions,
            runs=self.runs,
            items=self.items,
            events=self.events,
            candidates=self.candidates,
            listings=self.listings,
            policy=load_search_profile_policy(),
            scoring=load_scoring_baseline(),
            events_registry=load_events_registry(),
            job_runtime=runtime,
            run_job_type="recommendation.run",
            score_policy_version="scoring-baseline-v1",
        )


def build_profile(
    *,
    owner_id: UUID | None = None,
    name: str = "Mi radar",
    zones: tuple[str, ...] = ("palermo",),
    budget_max: float | None = 1000.0,
    budget_min: float | None = None,
    min_rooms: int | None = 2,
    surface_min: float | None = None,
    surface_max: float | None = None,
    status: SearchProfileState = "active",
    created_at: datetime | None = None,
    version: int = 1,
    profile_id: UUID | None = None,
) -> SearchProfile:
    now = created_at or datetime.now(timezone.utc)
    return SearchProfile(
        profile_id=profile_id or uuid4(),
        owner_id=owner_id or uuid4(),
        name=name,
        operation="rental",
        zones=zones,
        budget_max=budget_max,
        budget_min=budget_min,
        min_rooms=min_rooms,
        surface_min=surface_min,
        surface_max=surface_max,
        status=status,
        unknown_strategy={
            "price": "exclude",
            "location": "exclude",
            "rooms": "include",
            "surface": "include",
        },
        version=version,
        created_at=now,
        updated_at=now,
        current_version_id=None,
        latest_run_id=None,
        correlation_id=uuid4(),
    )


def build_listing(
    *,
    listing_id: UUID | None = None,
    total_cost: float = 700.0,
    neighborhood: str | None = "palermo",
    rooms: int | None = 2,
    surface_m2: float | None = 50.0,
    geo_precision: GeoPrecision = "neighborhood",
    operation: OperationType = "rental",
    property_type: PropertyType = "apartment",
) -> NormalizedListing:
    return NormalizedListing(
        listing_id=listing_id or uuid4(),
        canonical_property_id=uuid4(),
        run_id=uuid4(),
        snapshot_id=uuid4(),
        source=__import__(
            "umbral.application.ingestion.contracts", fromlist=["SourceIdentity"]
        ).SourceIdentity(
            source_id="fixture",
            source_version="1",
            contract_version="1",
        ),
        external_id="ext-1",
        url=None,
        published_at=None,
        last_observed_at=datetime.now(timezone.utc),
        normalizer_version="silver-schema-v1",
        operation=operation,
        property_type=property_type,
        price_value=total_cost,
        price_currency="ARS",
        expenses_value=None,
        expenses_currency=None,
        total_cost=total_cost,
        price_assumptions={},
        surface_m2=surface_m2,
        rooms=rooms,
        bedrooms=None,
        floor=None,
        amenities=(),
        description_text=None,
        location_text="",
        neighborhood=neighborhood,
        geo_precision=geo_precision,
        geometry=None,
        geo_source=None,
        normalization_errors=(),
    )
