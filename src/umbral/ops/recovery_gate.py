"""Recovery-point gate for production promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from umbral.ops.backup import BackupManifest


@dataclass(frozen=True, slots=True)
class RecoveryGateResult:
    passed: bool
    code: str
    backup_age_hours: float
    retention_valid: bool
    manifest_locked: bool


def evaluate_recovery_gate(
    manifest: BackupManifest, *, now: datetime | None = None
) -> RecoveryGateResult:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    created = manifest.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (instant - created).total_seconds() / 3600)
    retention_valid = instant <= manifest.retention_until
    locked = manifest.locked
    passed = age_hours <= manifest.policy.rpo_hours and retention_valid and locked
    code = "recovery.ready" if passed else "recovery.gate_failed"
    return RecoveryGateResult(passed, code, age_hours, retention_valid, locked)
