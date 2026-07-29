"""Local smoke and recovery gates (T101/T103)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from umbral.ops.backup import BackupManifest, BackupPolicy
from umbral.ops.recovery_gate import evaluate_recovery_gate
from umbral.ops.smoke import run_smoke


def _manifest(created_at: datetime, *, locked: bool = True) -> BackupManifest:
    return BackupManifest(
        backup_id="backup-test",
        created_at=created_at,
        source_namespace="primary",
        retention_until=created_at + timedelta(days=35),
        objects=(),
        database_dump_sha256=None,
        policy=BackupPolicy(),
        locked=locked,
    )


def test_smoke_requires_all_closed_checks_and_never_uses_product_data() -> None:
    names = (
        "web",
        "api",
        "worker",
        "scheduler",
        "extensions",
        "reference_job",
        "synthetic_object",
    )
    report = run_smoke({name: lambda: True for name in names})

    assert report.passed
    assert not report.product_data_used


def test_recovery_gate_enforces_rpo_lock_and_retention() -> None:
    created = datetime(2026, 7, 29, tzinfo=timezone.utc)
    assert evaluate_recovery_gate(
        _manifest(created), now=created + timedelta(hours=12)
    ).passed
    assert not evaluate_recovery_gate(
        _manifest(created), now=created + timedelta(hours=25)
    ).passed
    assert not evaluate_recovery_gate(
        _manifest(created, locked=False), now=created + timedelta(hours=1)
    ).passed
