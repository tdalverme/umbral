"""Local backup/restore drill tests (T060)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from umbral.ops.backup import BackupPolicy, create_backup
from umbral.ops.restore import restore_backup


def test_backup_manifest_and_restore_beside_primary_validate_checksums(
    tmp_path: Path,
) -> None:
    primary = tmp_path / "primary"
    object_path = primary / "objects" / "one" / "v1"
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"recovery bytes")
    database_dump = b"logical postgres dump"
    backup_root = tmp_path / "recovery"

    manifest = create_backup(
        source_root=primary,
        destination_root=backup_root,
        database_dump=database_dump,
        source_namespace="primary",
        policy=BackupPolicy(),
    )

    assert manifest.object_count == 1
    assert manifest.database_dump_sha256 == hashlib.sha256(database_dump).hexdigest()
    result = restore_backup(
        manifest_path=backup_root / "manifest.json",
        destination_root=tmp_path / "restores",
        namespace="drill-001",
        expected_alembic_head="0001_foundation_runtime",
    )

    restored = tmp_path / "restores" / "drill-001"
    assert result.checksums_verified == 1
    assert result.rto_within_sla
    assert (restored / "objects" / "one" / "v1").read_bytes() == b"recovery bytes"
    assert (restored / "database.dump").read_bytes() == database_dump
    assert result.alembic_head == "0001_foundation_runtime"
