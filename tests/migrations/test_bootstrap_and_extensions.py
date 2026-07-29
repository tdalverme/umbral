"""Bootstrap migration contract tests (T036).

The metadata assertions deliberately run without Docker.  The optional
PostgreSQL smoke is kept in the integration suite so a missing local Docker
daemon does not hide the deterministic migration contract.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

EXPECTED_TABLES = {
    "job_executions",
    "job_attempts",
    "job_outbox_messages",
    "job_schedules",
    "stored_objects",
    "stored_object_versions",
    "runtime_surface_status",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0001_foundation_runtime.py")
    spec = importlib.util.spec_from_file_location("foundation_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_revision_and_schema_inventory() -> None:
    revision = _revision_module()

    assert revision.revision == "0001_foundation_runtime"
    assert revision.down_revision is None
    assert set(revision.EXPECTED_TABLES) == EXPECTED_TABLES
    assert set(revision.REQUIRED_EXTENSIONS) == {"postgis", "vector"}


def test_bootstrap_is_transactional_and_has_explicit_empty_downgrade() -> None:
    revision = _revision_module()

    assert revision.TRANSACTIONAL is True
    assert revision.DOWNGRADE_POLICY == "empty-only"
    assert callable(revision.verify_bootstrap)
