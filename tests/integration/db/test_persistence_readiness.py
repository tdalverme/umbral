"""Persistence readiness checks are side-effect-free and sanitized (T040)."""

from __future__ import annotations

from umbral.infrastructure.db.readiness import (
    DatabaseReadiness,
    PersistenceProbe,
)


def test_persistence_probe_returns_allowlisted_checks_without_secrets() -> None:
    probe = PersistenceProbe(
        database=DatabaseReadiness(
            state="ready",
            code=None,
            details={"extension_postgis": "ready", "extension_vector": "ready"},
        ),
        alembic_head="0001_foundation_runtime",
    )

    report = probe.evaluate()

    assert report.state == "ready"
    assert report.alembic_head == "0001_foundation_runtime"
    assert set(report.checks) == {"postgres", "postgis", "pgvector", "alembic"}
    assert "postgresql://" not in repr(report)
    assert "password" not in repr(report).lower()


def test_persistence_probe_localizes_database_failure() -> None:
    probe = PersistenceProbe(
        database=DatabaseReadiness(
            state="unavailable",
            code="postgres.unavailable",
            details={},
        ),
        alembic_head=None,
    )

    report = probe.evaluate()

    assert report.state == "not_ready"
    assert report.checks["postgres"].code == "postgres.unavailable"
