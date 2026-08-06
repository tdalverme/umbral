"""Shared helpers for Silver normalization tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from tests.fakes.imports import InMemoryImportRunRepository
from umbral.application.ingestion.contracts import (
    ImportRun,
    ImportRunState,
    RawListingSnapshot,
    SourceIdentity,
)
from umbral.application.silver.contracts import NormalizedListing
from umbral.application.silver.silver_schema import (
    SilverSchemaSpec,
    normalize_snapshot,
)
from umbral.infrastructure.silver.contract_loader import load_silver_schema

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "silver"

DEFAULT_NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
_SCHEMA: SilverSchemaSpec | None = None


def silver_schema() -> SilverSchemaSpec:
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = load_silver_schema()
    return _SCHEMA


def load_records(name: str) -> list[dict[str, object]]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    records = raw.get("records")
    if not isinstance(records, list):
        raise ValueError("fixture must contain a records list")
    return [dict(item) for item in records if isinstance(item, dict)]


def snapshot_from_payload(
    payload: dict[str, object],
    *,
    run_id: UUID | None = None,
    source_id: str = "source-a",
    source_version: str = "v1",
    contract_version: str = "1",
    captured_at: datetime | None = None,
    snapshot_id: UUID | None = None,
) -> RawListingSnapshot:
    import hashlib

    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return RawListingSnapshot(
        snapshot_id=snapshot_id or uuid4(),
        run_id=run_id or uuid4(),
        source=SourceIdentity(source_id, source_version, contract_version),
        external_id=str(payload.get("external_id") or "record"),
        payload=payload,
        content_sha256=hashlib.sha256(content).hexdigest(),
        content_type="application/json",
        size_bytes=0,
        published_at=_parse_datetime(payload.get("published_at")),
        captured_at=captured_at or DEFAULT_NOW,
    )


def build_run(
    *,
    run_id: UUID | None = None,
    source_id: str = "source-a",
    state: ImportRunState = "succeeded",
) -> ImportRun:
    identifier = run_id or uuid4()
    return ImportRun(
        run_id=identifier,
        source=SourceIdentity(source_id, "v1", "1"),
        batch_key=f"batch-{identifier}",
        file_format="json",
        file_name="reference-batch.json",
        file_sha256="0" * 64,
        file_size_bytes=0,
        raw_storage_key="ingestion/raw/none",
        job_execution_id=None,
        state=state,
        created_at=DEFAULT_NOW,
        updated_at=DEFAULT_NOW,
        finished_at=DEFAULT_NOW if state in {"succeeded", "failed"} else None,
    )


def store_succeeded_run(runs: InMemoryImportRunRepository, run: ImportRun) -> ImportRun:
    """Register a run and mark it succeeded, mirroring the chained pipeline."""
    runs.create(
        run_id=run.run_id,
        source=run.source,
        batch_key=run.batch_key,
        file_format="json",
        file_name="reference-batch.json",
        file_sha256=run.file_sha256,
        file_size_bytes=0,
        raw_storage_key=run.raw_storage_key,
        job_execution_id=None,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
        now=run.created_at,
    )
    stored = runs.get(run.run_id)
    assert stored is not None
    stored.state = "succeeded"
    stored.finished_at = run.created_at
    runs.save(stored)
    return stored


def listing_from_payload(
    payload: dict[str, object],
    *,
    source_id: str = "source-a",
    run_id: UUID | None = None,
) -> NormalizedListing:
    snapshot = snapshot_from_payload(payload, run_id=run_id, source_id=source_id)
    fields = normalize_snapshot(snapshot, silver_schema())
    from umbral.application.silver.service import _build_listing

    return _build_listing(
        snapshot_id=snapshot.snapshot_id,
        run_id=snapshot.run_id,
        canonical_property_id=uuid4(),
        snapshot=snapshot,
        fields=fields,
        normalizer_version=silver_schema().normalizer_version,
        listing_id=uuid4(),
    )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
