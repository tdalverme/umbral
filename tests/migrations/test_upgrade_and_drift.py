"""Migration graph and metadata drift contracts (T037)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.config import Config
from alembic.script import ScriptDirectory

from umbral.infrastructure.db.base import metadata
from umbral.infrastructure.db.migrations import expected_schema


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0001_foundation_runtime.py")
    spec = importlib.util.spec_from_file_location("foundation_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script_directory() -> ScriptDirectory:
    config = Config(str(Path("alembic.ini")))
    config.set_main_option("script_location", "alembic")
    return ScriptDirectory.from_config(config)


def test_migration_graph_has_one_linear_head() -> None:
    heads = _script_directory().get_heads()

    assert heads == ["0017_urban_signals"]


def test_bootstrap_metadata_matches_declared_schema_without_drift() -> None:
    assert expected_schema() == metadata


def test_downgrade_policy_is_explicitly_empty_only() -> None:
    revision = _script_directory().get_revision("0001_foundation_runtime")

    assert revision is not None
    assert revision.down_revision is None
    assert "empty" in (revision.doc or "").lower()


def test_bootstrap_uses_an_immutable_schema_snapshot() -> None:
    revision = _revision_module()

    assert set(revision.TABLE_SNAPSHOT) == {
        "job_executions",
        "job_attempts",
        "job_outbox_messages",
        "job_schedules",
        "stored_objects",
        "stored_object_versions",
        "runtime_surface_status",
    }
    assert "expected_schema" not in Path(
        "alembic/versions/0001_foundation_runtime.py"
    ).read_text(encoding="utf-8")


def test_bootstrap_declares_closed_enum_domains_and_constraint_snapshot() -> None:
    revision = _revision_module()

    assert revision.ENUM_SNAPSHOT == {
        "actor_kind": {"system", "service", "operator"},
        "job_execution_state": {
            "pending",
            "queued",
            "running",
            "succeeded",
            "retry_wait",
            "failed",
        },
        "job_attempt_state": {
            "running",
            "succeeded",
            "transient_failure",
            "permanent_failure",
            "abandoned",
        },
        "job_outbox_state": {"pending", "publishing", "published", "failed"},
        "schedule_kind": {"one_shot", "fixed_interval"},
        "object_version_state": {"pending", "available", "failed"},
        "runtime_environment": {"local", "preview", "production"},
        "runtime_surface": {"web", "api", "worker", "scheduler"},
        "runtime_surface_state": {"ready", "degraded", "not_ready"},
    }
    assert "uq_job_executions_identity" in revision.CONSTRAINT_SNAPSHOT
    assert "ix_job_executions_state_available" in revision.CONSTRAINT_SNAPSHOT
