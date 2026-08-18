"""Production composition for the urban batch service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from umbral.application.criteria.contracts import ExtractionVersion
from umbral.application.urban.batch import UrbanBatchService
from umbral.application.urban.contract import UrbanContract
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyExtractionVersionRepository,
)
from umbral.infrastructure.db.repositories.urban import (
    SqlAlchemyNeighborhoodStatsRepository,
    SqlAlchemyUrbanContractRepository,
    SqlAlchemyUrbanListingReader,
    SqlAlchemyUrbanPrimitiveRepository,
    SqlAlchemyUrbanSignalRepository,
    SqlAlchemyUrbanSnapshotRepository,
)
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published
from umbral.infrastructure.urban.distance_calculator import SqlAlchemyDistanceCalculator

SessionFactory = Callable[[], Session]

_URBAN_EXTRACTION_KEY = "urban"


def build_urban_batch_service(
    *,
    session_factory: SessionFactory,
    contract: UrbanContract | None = None,
    correlation_id: UUID,
    created_at: datetime | None = None,
) -> UrbanBatchService:
    """Compose the batch service, resolving the active contract and urban version."""
    active_contract = contract or load_urban_contract_published()
    stamp = created_at or datetime.now(timezone.utc)

    contracts = SqlAlchemyUrbanContractRepository(session_factory)
    snapshot_repo = SqlAlchemyUrbanSnapshotRepository(session_factory)
    contract_row = contracts.active()
    if contract_row is None:
        contract_row = contracts.register(
            contract_version=active_contract.contract_version,
            payload=dict(asdict(active_contract)),
            correlation_id=correlation_id,
            now=stamp,
        )

    extraction_versions = SqlAlchemyExtractionVersionRepository(session_factory)
    version_id = _resolve_extraction_version(
        extraction_versions=extraction_versions,
        contract_version=active_contract.contract_version,
        correlation_id=correlation_id,
        now=stamp,
    )

    concepts = _signal_ref_concepts()
    return UrbanBatchService(
        contract=active_contract,
        distances=SqlAlchemyDistanceCalculator(session_factory, active_contract),
        primitives=SqlAlchemyUrbanPrimitiveRepository(session_factory),
        signals=SqlAlchemyUrbanSignalRepository(session_factory),
        stats=SqlAlchemyNeighborhoodStatsRepository(session_factory),
        contracts=contracts,
        snapshots=snapshot_repo,
        listings=SqlAlchemyUrbanListingReader(session_factory),
        extraction_version_id=version_id,
        concepts=concepts,
        created_at=stamp,
    )


def _resolve_extraction_version(
    *,
    extraction_versions: SqlAlchemyExtractionVersionRepository,
    contract_version: str,
    correlation_id: UUID,
    now: datetime,
) -> UUID:
    existing = extraction_versions.find(
        "urban", _URBAN_EXTRACTION_KEY, contract_version
    )
    if existing is not None:
        return existing.version_id
    version = ExtractionVersion(
        version_id=uuid4(),
        kind="urban",
        key=_URBAN_EXTRACTION_KEY,
        version=contract_version,
        payload={"artifact_version": contract_version},
        created_at=now,
        correlation_id=correlation_id,
        actor_kind="service",
        actor_id=None,
    )
    extraction_versions.insert(version)
    return version.version_id


def _signal_ref_concepts() -> Mapping[str, str]:
    result: dict[str, str] = {}
    for concept in load_concepts_seed().concepts:
        if concept.matcher_type != "signal_score":
            continue
        raw = concept.params_schema.get("signal_ref")
        if isinstance(raw, str) and raw:
            result[concept.key] = raw
    return result
