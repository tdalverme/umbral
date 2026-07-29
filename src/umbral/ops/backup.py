"""Private local backup manifest and immutable-object replication helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class BackupPolicy:
    """Recovery policy encoded into every manifest."""

    cadence_hours: int = 12
    retention_days: int = 35
    rpo_hours: int = 24
    rto_hours: int = 4

    def __post_init__(self) -> None:
        if self.cadence_hours <= 0 or self.retention_days <= 0:
            raise ValueError("backup cadence and retention must be positive")
        if self.rpo_hours <= 0 or self.rto_hours <= 0:
            raise ValueError("RPO and RTO must be positive")
        if self.cadence_hours > self.rpo_hours:
            raise ValueError("backup cadence cannot exceed RPO")


@dataclass(frozen=True, slots=True)
class BackupObjectEntry:
    relative_path: str
    sha256: str
    size_bytes: int
    is_metadata: bool = False


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_id: str
    created_at: datetime
    source_namespace: str
    retention_until: datetime
    objects: tuple[BackupObjectEntry, ...]
    database_dump_sha256: str | None
    policy: BackupPolicy
    alembic_head: str = "0001_foundation_runtime"
    database_row_counts: dict[str, int] | None = None
    locked: bool = True

    @property
    def object_count(self) -> int:
        return sum(not entry.is_metadata for entry in self.objects)

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self._payload())).hexdigest()

    def _payload(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at.isoformat(),
            "source_namespace": self.source_namespace,
            "retention_until": self.retention_until.isoformat(),
            "objects": [
                {
                    "relative_path": entry.relative_path,
                    "sha256": entry.sha256,
                    "size_bytes": entry.size_bytes,
                    "is_metadata": entry.is_metadata,
                }
                for entry in self.objects
            ],
            "database_dump_sha256": self.database_dump_sha256,
            "policy": {
                "cadence_hours": self.policy.cadence_hours,
                "retention_days": self.policy.retention_days,
                "rpo_hours": self.policy.rpo_hours,
                "rto_hours": self.policy.rto_hours,
            },
            "alembic_head": self.alembic_head,
            "database_row_counts": self.database_row_counts,
            "locked": self.locked,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["manifest_sha256"] = self.manifest_sha256
        return payload

    def write(self, path: Path) -> None:
        path.write_bytes(_canonical_json(self.to_dict()))

    @classmethod
    def read(cls, path: Path) -> BackupManifest:
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected = str(raw.pop("manifest_sha256", ""))
        manifest = _manifest_from_payload(raw)
        if expected != manifest.manifest_sha256:
            raise ValueError("backup manifest checksum mismatch")
        return manifest


def create_backup(
    *,
    source_root: str | Path,
    destination_root: str | Path,
    database_dump: bytes | None = None,
    source_namespace: str = "primary",
    policy: BackupPolicy | None = None,
    now: datetime | None = None,
    alembic_head: str = "0001_foundation_runtime",
    database_row_counts: dict[str, int] | None = None,
) -> BackupManifest:
    """Copy immutable objects and optional logical DB dump to a new manifest."""

    source = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    policy_value = policy or BackupPolicy()
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    destination.mkdir(parents=True, exist_ok=True)
    objects_source = source / "objects"
    objects_destination = destination / "objects"
    entries: list[BackupObjectEntry] = []
    if objects_source.is_dir():
        for path in sorted(
            item for item in objects_source.rglob("*") if item.is_file()
        ):
            relative = path.relative_to(source).as_posix()
            copied = objects_destination / path.relative_to(objects_source)
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copied)
            body = copied.read_bytes()
            entries.append(
                BackupObjectEntry(
                    relative_path=relative,
                    sha256=hashlib.sha256(body).hexdigest(),
                    size_bytes=len(body),
                    is_metadata=path.name.endswith(".meta.json"),
                )
            )
    database_digest: str | None = None
    if database_dump is not None:
        dump_path = destination / "database.dump"
        dump_path.write_bytes(database_dump)
        database_digest = hashlib.sha256(database_dump).hexdigest()
    manifest = BackupManifest(
        backup_id=f"backup-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        created_at=timestamp,
        source_namespace=source_namespace,
        retention_until=timestamp + timedelta(days=policy_value.retention_days),
        objects=tuple(entries),
        database_dump_sha256=database_digest,
        policy=policy_value,
        alembic_head=alembic_head,
        database_row_counts=database_row_counts,
    )
    manifest.write(destination / "manifest.json")
    (destination / ".retention.lock").write_text(
        manifest.retention_until.isoformat(), encoding="utf-8"
    )
    return manifest


def replicate_to_recovery(**kwargs: Any) -> BackupManifest:
    """Named operational alias for the twelve-hour primary-to-recovery copy."""

    return create_backup(**kwargs)


def _manifest_from_payload(raw: dict[str, Any]) -> BackupManifest:
    policy_raw = raw["policy"]
    entries = tuple(
        BackupObjectEntry(
            relative_path=str(item["relative_path"]),
            sha256=str(item["sha256"]),
            size_bytes=int(item["size_bytes"]),
            is_metadata=bool(item.get("is_metadata", False)),
        )
        for item in raw["objects"]
    )
    return BackupManifest(
        backup_id=str(raw["backup_id"]),
        created_at=datetime.fromisoformat(str(raw["created_at"])),
        source_namespace=str(raw["source_namespace"]),
        retention_until=datetime.fromisoformat(str(raw["retention_until"])),
        objects=entries,
        database_dump_sha256=(
            str(raw["database_dump_sha256"])
            if raw.get("database_dump_sha256") is not None
            else None
        ),
        policy=BackupPolicy(**{key: int(value) for key, value in policy_raw.items()}),
        alembic_head=str(raw.get("alembic_head", "0001_foundation_runtime")),
        database_row_counts=raw.get("database_row_counts"),
        locked=bool(raw.get("locked", True)),
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
