"""Shared builder for criteria service unit tests with in-memory adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.fakes.criteria import (
    FakeCompilationRepository,
    FakeConceptRepository,
    FakeEventRepository,
    FakeExtractionVersionRepository,
    FakeFactRepository,
    FakeListingReader,
    FakeObservationRepository,
    FakeProfileSnapshotReader,
    FakeRecomputeRunRepository,
)
from umbral.application.criteria.service import CriteriaService, EmbeddingModel
from umbral.application.ingestion.contracts import SourceIdentity
from umbral.application.silver.contracts import NormalizedListing
from umbral.infrastructure.criteria.contract_loader import (
    load_concepts_seed,
    load_extraction_contract,
    load_matcher_types,
)
from umbral.infrastructure.criteria.extractors.fake import FakeStructuredExtractor
from umbral.infrastructure.radar.contract_loader import load_events_registry


def build_listing(
    *,
    description_text: str | None = None,
    rooms: int | None = None,
    floor: int | None = None,
    amenities: tuple[str, ...] = (),
    normalizer_version: str = "silver-v1",
    listing_id: UUID | None = None,
) -> NormalizedListing:
    return NormalizedListing(
        listing_id=listing_id or uuid4(),
        canonical_property_id=uuid4(),
        run_id=uuid4(),
        snapshot_id=uuid4(),
        source=SourceIdentity(
            source_id="source-a", source_version="v1", contract_version="1"
        ),
        external_id=f"ext-{uuid4()}",
        url=None,
        published_at=None,
        last_observed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        normalizer_version=normalizer_version,
        operation="rental",
        property_type="apartment",
        price_value=500000,
        price_currency="ARS",
        expenses_value=None,
        expenses_currency=None,
        total_cost=500000,
        price_assumptions={},
        surface_m2=45.0,
        rooms=rooms,
        bedrooms=None,
        floor=floor,
        amenities=amenities,
        description_text=description_text,
        location_text="Caballito",
        neighborhood="Caballito",
        geo_precision="neighborhood",
        geometry=None,
        geo_source=None,
        normalization_errors=(),
    )


class CriteriaTestContext:
    def __init__(
        self,
        *,
        extractor: FakeStructuredExtractor | None = None,
        default_extractor: bool = True,
        embedding_model: EmbeddingModel | None = None,
        embeddings_enabled: bool = False,
        urban_context_enabled: bool = False,
    ) -> None:
        self.concepts = FakeConceptRepository()
        self.facts = FakeFactRepository()
        self.compilations = FakeCompilationRepository()
        self.observations = FakeObservationRepository()
        self.extraction_versions = FakeExtractionVersionRepository()
        self.recomputes = FakeRecomputeRunRepository()
        self.events = FakeEventRepository()
        self.observations.recompute_runs = self.recomputes
        self.observations.events = self.events
        self.listings = FakeListingReader()
        self.profiles = FakeProfileSnapshotReader()
        self.extractor = (
            extractor
            if extractor is not None
            else (
                FakeStructuredExtractor(
                    {
                        "luminosidad": {
                            "value": "media",
                            "evidence": "luminoso",
                            "confidence": 0.8,
                        },
                        "estado_general": {
                            "value": "bueno",
                            "evidence": "en buen estado",
                            "confidence": 0.9,
                        },
                    }
                )
                if default_extractor
                else None
            )
        )
        self.service = CriteriaService(
            concepts=self.concepts,
            facts=self.facts,
            compilations=self.compilations,
            observations=self.observations,
            extraction_versions=self.extraction_versions,
            recomputes=self.recomputes,
            events=self.events,
            listings=self.listings,
            profiles=self.profiles,
            concepts_seed=load_concepts_seed(),
            matcher_types=load_matcher_types(),
            extraction_contract=load_extraction_contract(),
            events_registry=load_events_registry(),
            extractor=self.extractor,
            embedding_model=embedding_model,
            embeddings_enabled=embeddings_enabled,
            urban_context_enabled=urban_context_enabled,
            job_runtime=None,
        )

    def seed_concepts(self) -> None:
        self.service.seed_registry(correlation_id=uuid4())

    def add_listing(
        self,
        *,
        description_text: str | None = None,
        rooms: int | None = None,
        floor: int | None = None,
        amenities: tuple[str, ...] = (),
        normalizer_version: str = "silver-v1",
    ) -> NormalizedListing:
        listing = build_listing(
            description_text=description_text,
            rooms=rooms,
            floor=floor,
            amenities=amenities,
            normalizer_version=normalizer_version,
        )
        self.listings.listings[listing.listing_id] = listing
        return listing
