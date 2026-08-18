"""Composition helper for the criteria service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from umbral.application.criteria.extractor import StructuredExtractor
from umbral.application.criteria.service import CriteriaService
from umbral.application.jobs.ports import JobRuntime
from umbral.infrastructure.criteria.contract_loader import (
    load_concepts_seed,
    load_extraction_contract,
    load_matcher_types,
)
from umbral.infrastructure.criteria.extractors.fake import FakeStructuredExtractor
from umbral.infrastructure.criteria.extractors.managed import (
    ManagedStructuredExtractor,
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
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Any]


def build_extractor(provider: str, **settings: object) -> StructuredExtractor:
    """Select the provider adapter; ``fake`` is the local/CI default."""

    if provider == "fake":
        return FakeStructuredExtractor()
    if provider == "managed":
        return ManagedStructuredExtractor(
            endpoint=str(settings["endpoint"]),
            api_key=str(settings["api_key"]),
            model=str(settings["model"]),
        )
    raise ValueError(f"unsupported extraction provider: {provider}")


def build_criteria_service(
    *,
    session_factory: SessionFactory,
    job_runtime: JobRuntime | None,
    extraction_provider: str = "fake",
    extraction_endpoint: str | None = None,
    extraction_api_key: str | None = None,
    extraction_model: str | None = None,
    qualitative_max_attempts: int = 2,
    batch_size: int = 250,
    extraction_job_type: str = "extraction.run",
    recompute_job_type: str = "extraction.recompute",
    embeddings_enabled: bool = False,
    embedding_model_version_key: str | None = None,
    urban_context_enabled: bool = False,
    extractor: StructuredExtractor | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CriteriaService:
    if extractor is None:
        extractor = build_extractor(
            extraction_provider,
            endpoint=extraction_endpoint or "",
            api_key=extraction_api_key or "",
            model=extraction_model or "",
        )
    return CriteriaService(
        concepts=SqlAlchemyConceptRepository(session_factory),
        facts=SqlAlchemyFactRepository(session_factory),
        compilations=SqlAlchemyCompilationRepository(session_factory),
        observations=SqlAlchemyObservationRepository(session_factory),
        extraction_versions=SqlAlchemyExtractionVersionRepository(session_factory),
        recomputes=SqlAlchemyRecomputeRunRepository(session_factory),
        events=SqlAlchemyEventRepository(session_factory),
        listings=SqlAlchemyCriteriaListingReader(session_factory),
        profiles=SqlAlchemyProfileSnapshotReader(session_factory),
        concepts_seed=load_concepts_seed(),
        matcher_types=load_matcher_types(),
        extraction_contract=load_extraction_contract(),
        events_registry=load_events_registry(),
        extractor=extractor,
        embeddings=(
            SqlAlchemyEmbeddingRepository(session_factory)
            if embeddings_enabled
            else None
        ),
        urban_signals=None,
        job_runtime=job_runtime,
        extraction_job_type=extraction_job_type,
        recompute_job_type=recompute_job_type,
        qualitative_max_attempts=qualitative_max_attempts,
        batch_size=batch_size,
        embeddings_enabled=embeddings_enabled,
        embedding_model_version_key=embedding_model_version_key,
        urban_context_enabled=urban_context_enabled,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )
