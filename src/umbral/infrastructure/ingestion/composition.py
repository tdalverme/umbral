"""Composition helper for the ingestion application service with SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from umbral.application.ingestion.import_contract import ContractSpec
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.ports import JobRuntime
from umbral.application.objects.ports import ObjectStore
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyQuarantineRepository,
    SqlAlchemyRawSnapshotRepository,
)
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1
from umbral.infrastructure.sources.file_source import FileImportSource

SessionFactory = Callable[[], Any]


def build_ingestion_service(
    *,
    session_factory: SessionFactory,
    object_store: ObjectStore,
    job_runtime: JobRuntime | None = None,
    contract: ContractSpec | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ImportRunService:
    return ImportRunService(
        runs=SqlAlchemyImportRunRepository(session_factory),
        snapshots=SqlAlchemyRawSnapshotRepository(session_factory),
        quarantine=SqlAlchemyQuarantineRepository(session_factory),
        source=FileImportSource(),
        contract=contract or load_contract_v1(),
        objects=object_store,
        job_runtime=job_runtime,
        clock=clock or (lambda: datetime.now(timezone.utc)),
    )
