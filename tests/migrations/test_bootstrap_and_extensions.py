"""Bootstrap migration contract tests (T036).

The metadata assertions deliberately run without Docker.  The optional
PostgreSQL smoke is kept in the integration suite so a missing local Docker
daemon does not hide the deterministic migration contract.
"""

from __future__ import annotations

import importlib


EXPECTED_TABLES = {
    "job_executions",
    "job_attempts",
    "job_outbox_messages",
    "job_schedules",
    "stored_objects",
    "stored_object_versions",
    "runtime_surface_status",
}


def test_bootstrap_revision_and_schema_inventory() -> None:
    revision = importlib.import_module("alembic.versions.0001_foundation_runtime")

    assert revision.revision == "0001_foundation_runtime"
    assert revision.down_revision is None
    assert set(revision.EXPECTED_TABLES) == EXPECTED_TABLES
    assert set(revision.REQUIRED_EXTENSIONS) == {"postgis", "vector"}


def test_bootstrap_is_transactional_and_has_explicit_empty_downgrade() -> None:
    revision = importlib.import_module("alembic.versions.0001_foundation_runtime")

    assert revision.TRANSACTIONAL is True
    assert revision.DOWNGRADE_POLICY == "empty-only"
    assert callable(revision.verify_bootstrap)

