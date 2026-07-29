"""Beside-primary restore validation for backup manifests."""

from __future__ import annotations

import hashlib
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from umbral.ops.backup import BackupManifest


class RestoreValidationError(RuntimeError):
    """A recovery artifact failed validation before cutover."""


@dataclass(frozen=True, slots=True)
class RestoreResult:
    namespace: str
    checksums_verified: int
    object_count: int
    elapsed_seconds: float
    rpo_age_hours: float
    rto_within_sla: bool
    alembic_head: str
    database_row_counts: dict[str, int] | None


def restore_backup(
    *,
    manifest_path: str | Path,
    destination_root: str | Path,
    namespace: str,
    expected_alembic_head: str | None = None,
    now: datetime | None = None,
) -> RestoreResult:
    """Restore objects and dump into a new namespace, never over primary."""

    started = time.perf_counter()
    path = Path(manifest_path).resolve()
    manifest = BackupManifest.read(path)
    measured_at = now or datetime.now(timezone.utc)
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)
    if (
        expected_alembic_head is not None
        and manifest.alembic_head != expected_alembic_head
    ):
        raise RestoreValidationError("backup Alembic head does not match expected head")
    if not namespace or namespace in {"primary", "production"}:
        raise RestoreValidationError("restore namespace must be beside primary")
    destination = Path(destination_root).resolve() / namespace
    if destination.exists():
        raise RestoreValidationError("restore namespace already exists")
    destination.mkdir(parents=True)
    try:
        source_root = path.parent
        checksums_verified = 0
        for entry in manifest.objects:
            source = _safe_child(source_root, entry.relative_path)
            if not source.is_file():
                raise RestoreValidationError("backup object is missing")
            body = source.read_bytes()
            if (
                len(body) != entry.size_bytes
                or hashlib.sha256(body).hexdigest() != entry.sha256
            ):
                raise RestoreValidationError("backup object checksum mismatch")
            target = _safe_child(destination, entry.relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            checksums_verified += 1 if not entry.is_metadata else 0
        if manifest.database_dump_sha256 is not None:
            source_dump = source_root / "database.dump"
            if not source_dump.is_file():
                raise RestoreValidationError("logical database dump is missing")
            dump = source_dump.read_bytes()
            if hashlib.sha256(dump).hexdigest() != manifest.database_dump_sha256:
                raise RestoreValidationError("logical database dump checksum mismatch")
            (destination / "database.dump").write_bytes(dump)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    elapsed = time.perf_counter() - started
    rpo_age_hours = max(
        0.0,
        (measured_at - manifest.created_at).total_seconds() / 3600,
    )
    return RestoreResult(
        namespace=namespace,
        checksums_verified=checksums_verified,
        object_count=manifest.object_count,
        elapsed_seconds=elapsed,
        rpo_age_hours=rpo_age_hours,
        rto_within_sla=(
            elapsed <= manifest.policy.rto_hours * 3600
            and rpo_age_hours <= manifest.policy.rpo_hours
        ),
        alembic_head=manifest.alembic_head,
        database_row_counts=manifest.database_row_counts,
    )


def restore_beside_primary(**kwargs: Any) -> RestoreResult:
    """Operational alias emphasizing that restore never overwrites primary."""

    return restore_backup(**kwargs)


def _safe_child(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise RestoreValidationError("recovery path escapes namespace") from error
    return candidate
