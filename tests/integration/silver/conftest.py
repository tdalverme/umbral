"""Shared Postgres backend and Bronze seeding for Silver integration tests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection
from tests.support.silver import build_run

from umbral.application.ingestion.contracts import (
    ImportRunSnapshot,
    RawListingSnapshot,
)
from umbral.application.ingestion.import_contract import validate_record
from umbral.application.silver.dedupe_policy import DedupePolicySpec
from umbral.application.silver.ports import Geocoder
from umbral.application.silver.service import NormalizeRunService
from umbral.application.silver.silver_schema import SilverSchemaSpec
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
from umbral.infrastructure.ingestion.contract_loader import load_contract_v2
from umbral.infrastructure.object_store.filesystem import FilesystemObjectStore
from umbral.infrastructure.silver.contract_loader import (
    load_dedupe_policy,
    load_silver_schema,
)

SessionFactory = Callable[[], Session]
SilverBackend = tuple[SessionFactory, FilesystemObjectStore]

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "silver"
_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
_seed_counter = 0


@pytest.fixture
def silver_backend(request: pytest.FixtureRequest, tmp_path: Path) -> SilverBackend:
    """Postgres at head plus a filesystem object store for one test."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)
    object_store = FilesystemObjectStore(str(tmp_path / "objects"))

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory, object_store


def import_batch(
    factory: SessionFactory,
    _object_store: FilesystemObjectStore,
    *,
    name: str,
    source_id: str,
    batch_key: str,
) -> ImportRunSnapshot:
    """Seed a succeeded import run + Bronze snapshots for one fixture.

    Mirrors Bronze acceptance (validation, intra-lot dedupe, cross-run
    dedupe by ``(source_id, external_id, content_sha256)``) directly through
    the real repositories, so Silver integration tests exercise Postgres and
    migration 0004 without depending on Bronze's worker job runtime.
    """
    global _seed_counter
    del _object_store
    _seed_counter += 1
    captured_at = _NOW + timedelta(minutes=_seed_counter)
    contract = load_contract_v2()
    raw_records = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    records = [
        dict(item)
        for item in raw_records.get("records", [])
        if isinstance(item, dict)
    ]

    run = build_run(source_id=source_id)
    run_repo = SqlAlchemyImportRunRepository(factory)
    existing = run_repo.get_by_identity(source_id, batch_key)
    if existing is not None:
        return existing.snapshot()
    created = run_repo.create(
        run_id=run.run_id,
        source=run.source,
        batch_key=batch_key,
        file_format="json",
        file_name=name,
        file_sha256=hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(),
        file_size_bytes=0,
        raw_storage_key=f"objects/raw/{run.run_id}",
        job_execution_id=None,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
        now=_NOW,
    )

    snapshot_repo = SqlAlchemyRawSnapshotRepository(factory)
    seen: set[tuple[str, str]] = set()
    accepted = 0
    quarantined = 0
    duplicates = 0
    missing_total = 0
    for payload in records:
        external_id = str(payload.get("external_id") or "record")
        content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        sha = hashlib.sha256(content).hexdigest()
        key = (external_id, sha)
        if key in seen or snapshot_repo.exists(
            source_id=source_id, external_id=external_id, content_sha256=sha
        ):
            duplicates += 1
            continue
        result = validate_record(payload, contract)
        if not result.valid:
            quarantined += 1
            continue
        snapshot_repo.insert(
            RawListingSnapshot(
                snapshot_id=uuid4(),
                run_id=created.run_id,
                source=created.source,
                external_id=external_id,
                payload=payload,
                content_sha256=sha,
                content_type="application/json",
                size_bytes=len(content),
                published_at=_parse_datetime(payload.get("published_at")),
                captured_at=captured_at,
            )
        )
        accepted += 1
        missing_total += result.missing_optional
        seen.add(key)

    created.total_records = len(records)
    created.accepted = accepted
    created.quarantined = quarantined
    created.duplicates = duplicates
    created.missing_fields = missing_total
    created.state = "succeeded"
    created.finished_at = _NOW
    run_repo.save(created)
    return created.snapshot()


def normalize_service(
    factory: SessionFactory,
    *,
    schema: SilverSchemaSpec | None = None,
    dedupe: DedupePolicySpec | None = None,
    geocoder: Geocoder | None = None,
) -> NormalizeRunService:
    return NormalizeRunService(
        listings=SqlAlchemySilverListingRepository(factory),
        canonicals=SqlAlchemyCanonicalPropertyRepository(factory),
        links=SqlAlchemyDedupeLinkRepository(factory),
        changes=SqlAlchemyChangeRepository(factory),
        snapshots=SqlAlchemyRawSnapshotRepository(factory),
        runs=SqlAlchemyImportRunRepository(factory),
        schema=schema or load_silver_schema(),
        dedupe=dedupe or load_dedupe_policy(),
        geocoder=geocoder,
        clock=lambda: _NOW,
    )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
