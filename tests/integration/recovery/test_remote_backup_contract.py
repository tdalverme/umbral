"""Static safety contracts for the remote Neon-to-R2 backup scripts."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKUP_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "backup-preview.ps1"
MIGRATE_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "migrate-preview.ps1"
CHECK_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "check-preview-dependencies.ps1"


def test_remote_backup_uses_direct_url_and_local_sha256_with_head_verification(
) -> None:
    script = BACKUP_SCRIPT.read_text(encoding="utf-8")

    assert "DATABASE_MIGRATION_URL" in script
    assert "pg_dump" in script
    assert "--format=custom" in script
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "head-object" in script
    assert "R2_RECOVERY_BUCKET" in script
    assert "DATABASE_URL" not in script


def test_migration_uses_direct_url_only_after_backup_evidence_and_checks_extensions(
) -> None:
    script = MIGRATE_SCRIPT.read_text(encoding="utf-8")

    assert "DATABASE_MIGRATION_URL" in script
    assert "alembic upgrade head" in script
    assert "backup evidence" in script.lower()
    assert "postgis" in script
    assert "vector" in script
    assert "$env:DATABASE_URL = $env:DATABASE_MIGRATION_URL" in script
    assert "$env:PYTHONPATH" in script


def test_dependency_script_writes_sanitized_json_evidence() -> None:
    script = CHECK_SCRIPT.read_text(encoding="utf-8")

    assert "umbral.ops.provider_conformance" in script
    assert "EvidencePath" in script
    assert "ConvertTo-Json" in script
