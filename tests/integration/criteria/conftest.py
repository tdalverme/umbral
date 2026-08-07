"""Shared Postgres backend and Silver seeding for criteria integration tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection
from tests.support.criteria import build_listing

from umbral.application.criteria.service import CriteriaService
from umbral.infrastructure.criteria.contract_loader import (
    load_concepts_seed,
    load_extraction_contract,
    load_matcher_types,
)
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyCompilationRepository,
    SqlAlchemyConceptRepository,
    SqlAlchemyCriteriaListingReader,
    SqlAlchemyEmbeddingRepository,
    SqlAlchemyExtractionVersionRepository,
    SqlAlchemyFactRepository,
    SqlAlchemyObservationRepository,
    SqlAlchemyProfileSnapshotReader,
    SqlAlchemyRecomputeRunRepository,
    SqlAlchemyUrbanSignalRepository,
)
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyRawSnapshotRepository,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.db.repositories.silver import (
    SqlAlchemyCanonicalPropertyRepository,
    SqlAlchemySilverListingRepository,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def criteria_backend(request: pytest.FixtureRequest) -> SessionFactory:
    """Postgres at head for one criteria integration test."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory


def seed_silver_listings(
    factory: SessionFactory,
    *,
    texts: list[str] | None = None,
    normalizer_version: str = "silver-v1",
    count: int = 3,
) -> list[UUID]:
    """Insert one import run + canonical properties + silver listings."""
    from tests.support.silver import build_run

    from umbral.application.ingestion.contracts import RawListingSnapshot

    texts = texts or [
        "Departamento con balcon y cocina separada en Caballito.",
        "Monoambiente sin balcon, luminoso.",
        "Piso luminoso en el piso 5 con ascensor.",
    ]
    run_repo = SqlAlchemyImportRunRepository(factory)
    import_run = run_repo.create(
        run_id=uuid4(),
        source=build_run(source_id="fixture").source,
        batch_key="criteria-seed",
        file_format="json",
        file_name="criteria-seed.json",
        file_sha256="0" * 64,
        file_size_bytes=0,
        raw_storage_key=f"objects/raw/{uuid4()}",
        job_execution_id=None,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
        now=_NOW,
    )
    snapshots = SqlAlchemyRawSnapshotRepository(factory)
    canonicals = SqlAlchemyCanonicalPropertyRepository(factory)
    listings = SqlAlchemySilverListingRepository(factory)
    listing_ids: list[UUID] = []
    for index in range(count):
        canonical = canonicals.create(
            canonical_property_id=uuid4(),
            first_seen_at=_NOW,
            correlation_id=uuid4(),
            actor_kind="system",
            actor_id=None,
        )
        snapshot_id = uuid4()
        snapshots.insert(
            RawListingSnapshot(
                snapshot_id=snapshot_id,
                run_id=import_run.run_id,
                source=import_run.source,
                external_id=f"criteria-{index}",
                payload={},
                content_sha256="0" * 64,
                content_type="application/json",
                size_bytes=0,
                published_at=_NOW,
                captured_at=_NOW,
            )
        )
        listing = build_listing(
            description_text=texts[index % len(texts)],
            rooms=2 + (index % 2),
            floor=(5 if index == 2 else None),
            normalizer_version=normalizer_version,
        )
        from dataclasses import replace

        listing = replace(
            listing,
            canonical_property_id=canonical.canonical_property_id,
            run_id=import_run.run_id,
            snapshot_id=snapshot_id,
            source=import_run.source,
        )
        listings.insert(listing)
        listing_ids.append(listing.listing_id)
    return listing_ids


def build_criteria_service(
    factory: SessionFactory,
    *,
    extractor: object | None = None,
    embeddings_enabled: bool = False,
    embedding_model: object | None = None,
    urban_context_enabled: bool = False,
    urban_source: object | None = None,
) -> CriteriaService:
    from umbral.infrastructure.criteria.extractors.fake import FakeStructuredExtractor

    active_extractor = extractor or FakeStructuredExtractor(
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
    return CriteriaService(
        concepts=SqlAlchemyConceptRepository(factory),
        facts=SqlAlchemyFactRepository(factory),
        compilations=SqlAlchemyCompilationRepository(factory),
        observations=SqlAlchemyObservationRepository(factory),
        extraction_versions=SqlAlchemyExtractionVersionRepository(factory),
        recomputes=SqlAlchemyRecomputeRunRepository(factory),
        events=SqlAlchemyEventRepository(factory),
        listings=SqlAlchemyCriteriaListingReader(factory),
        profiles=SqlAlchemyProfileSnapshotReader(factory),
        concepts_seed=load_concepts_seed(),
        matcher_types=load_matcher_types(),
        extraction_contract=load_extraction_contract(),
        events_registry=load_events_registry(),
        extractor=active_extractor,  # type: ignore[arg-type]
        embeddings=(
            SqlAlchemyEmbeddingRepository(factory) if embeddings_enabled else None
        ),
        embedding_model=embedding_model,  # type: ignore[arg-type]
        urban_signals=(
            SqlAlchemyUrbanSignalRepository(factory) if urban_context_enabled else None
        ),
        urban_source=urban_source,  # type: ignore[arg-type]
        embeddings_enabled=embeddings_enabled,
        urban_context_enabled=urban_context_enabled,
        job_runtime=None,
    )
