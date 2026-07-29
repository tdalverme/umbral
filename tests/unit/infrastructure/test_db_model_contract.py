"""PostgreSQL model type and constraint contracts."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM, JSONB

from umbral.infrastructure.db.base import metadata


def test_state_columns_use_closed_postgresql_enums() -> None:
    expected = {
        "job_executions": ("state", "job_execution_state"),
        "job_attempts": ("state", "job_attempt_state"),
        "job_outbox_messages": ("state", "job_outbox_state"),
        "job_schedules": ("schedule_kind", "schedule_kind"),
        "stored_object_versions": ("state", "object_version_state"),
        "runtime_surface_status": ("state", "runtime_surface_state"),
    }

    for table_name, (column_name, enum_name) in expected.items():
        column = metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, ENUM)
        assert column.type.name == enum_name
        assert column.type.create_type is True

    actor_type = metadata.tables["job_executions"].c.actor_kind.type
    assert isinstance(actor_type, ENUM)
    assert actor_type.name == "actor_kind"


def test_json_payloads_are_postgresql_jsonb_and_constraints_are_named() -> None:
    assert isinstance(metadata.tables["job_executions"].c.result_summary.type, JSONB)
    assert isinstance(metadata.tables["runtime_surface_status"].c.checks.type, JSONB)

    execution = metadata.tables["job_executions"]
    constraints = {constraint.name for constraint in execution.constraints}
    assert "uq_job_executions_identity" in constraints
    assert "ck_job_executions_attempt_bounds" in constraints
    assert "ix_job_executions_state_available" in {
        index.name for index in execution.indexes
    }
