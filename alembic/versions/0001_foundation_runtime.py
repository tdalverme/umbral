"""Foundation runtime PostgreSQL bootstrap; empty-only downgrade.

This revision is an immutable schema snapshot.  It intentionally does not
import ORM metadata: future model edits must arrive in a new Alembic revision
and cannot silently rewrite an already-published bootstrap.
"""

from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import NoInspectionAvailable

revision = "0001_foundation_runtime"
down_revision = None
branch_labels = None
depends_on = None

TABLE_SNAPSHOT = (
    "job_executions",
    "job_attempts",
    "job_outbox_messages",
    "job_schedules",
    "stored_objects",
    "stored_object_versions",
    "runtime_surface_status",
)
# Compatibility name used by existing migration metadata checks.  The tuple is
# immutable and remains the published snapshot source of truth.
EXPECTED_TABLES = TABLE_SNAPSHOT
REQUIRED_EXTENSIONS = ("postgis", "vector")
TRANSACTIONAL = True
DOWNGRADE_POLICY = "empty-only"

ENUM_SNAPSHOT = {
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

CONSTRAINT_SNAPSHOT = {
    "uq_job_executions_identity",
    "ck_job_executions_attempt_bounds",
    "ck_job_executions_max_attempts",
    "ck_job_executions_terminal_finished",
    "ck_job_executions_running_lease",
    "uq_job_attempts_execution_ordinal",
    "ck_job_attempts_ordinal",
    "ck_job_attempts_duration",
    "uq_job_outbox_execution_attempt",
    "ck_job_outbox_attempt_number",
    "ck_job_outbox_publish_attempts",
    "ck_job_schedules_interval",
    "ck_job_schedules_kind",
    "ck_job_schedules_max_attempts",
    "ck_stored_objects_purpose",
    "uq_stored_object_versions_storage_key",
    "ck_stored_object_versions_size",
    "ck_stored_object_versions_sha256",
    "ck_stored_object_versions_available_at",
    "ck_runtime_surface_environment",
    "ck_runtime_surface_surface",
    "ck_runtime_surface_state",
    "ix_job_executions_state_available",
    "ix_job_executions_state_lease",
    "ix_job_executions_correlation",
}

INDEX_SNAPSHOT = {
    "ix_job_executions_state_available",
    "ix_job_executions_state_lease",
    "ix_job_executions_correlation",
    "ix_job_attempts_correlation_started",
    "ix_job_outbox_state_available",
    "ix_job_schedules_due",
    "ix_stored_object_versions_object_created",
    "ix_stored_object_versions_state_created",
    "ix_stored_object_versions_correlation",
    "ix_runtime_surface_observed",
}

_ENUM_VALUES = {
    "actor_kind": ("system", "service", "operator"),
    "job_execution_state": (
        "pending",
        "queued",
        "running",
        "succeeded",
        "retry_wait",
        "failed",
    ),
    "job_attempt_state": (
        "running",
        "succeeded",
        "transient_failure",
        "permanent_failure",
        "abandoned",
    ),
    "job_outbox_state": ("pending", "publishing", "published", "failed"),
    "schedule_kind": ("one_shot", "fixed_interval"),
    "object_version_state": ("pending", "available", "failed"),
    "runtime_environment": ("local", "preview", "production"),
    "runtime_surface": ("web", "api", "worker", "scheduler"),
    "runtime_surface_state": ("ready", "degraded", "not_ready"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUM_VALUES[name], name=name, create_type=False)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> tuple[sa.Column[Any], ...]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_kind", _enum("actor_kind"), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    )


def _create_types() -> None:
    for name, values in _ENUM_VALUES.items():
        quoted_values = ", ".join("'" + value + "'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({quoted_values})")


def upgrade() -> None:
    bind = op.get_bind()
    for extension in REQUIRED_EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
    _create_types()

    op.create_table(
        "job_executions",
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("logical_target", sa.String(300), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("state", _enum("job_execution_state"), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False),
        sa.Column("max_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", _uuid(), primary_key=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "job_type",
            "logical_target",
            "idempotency_key",
            name="uq_job_executions_identity",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_job_executions_attempt_bounds",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_job_executions_max_attempts",
        ),
        sa.CheckConstraint(
            "(state IN ('succeeded', 'failed') AND finished_at IS NOT NULL) OR "
            "(state NOT IN ('succeeded', 'failed') AND finished_at IS NULL)",
            name="ck_job_executions_terminal_finished",
        ),
        sa.CheckConstraint(
            "(state = 'running' AND lease_owner IS NOT NULL "
            "AND lease_until IS NOT NULL) OR "
            "(state <> 'running' OR (lease_owner IS NULL AND lease_until IS NULL))",
            name="ck_job_executions_running_lease",
        ),
    )
    op.create_index(
        "ix_job_executions_state_available",
        "job_executions",
        ["state", "available_at"],
    )
    op.create_index(
        "ix_job_executions_state_lease", "job_executions", ["state", "lease_until"]
    )
    op.create_index(
        "ix_job_executions_correlation", "job_executions", ["correlation_id"]
    )

    op.create_table(
        "job_attempts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "execution_id",
            _uuid(),
            sa.ForeignKey("job_executions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("transport_message_id", sa.String(200), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("state", _enum("job_attempt_state"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("release_id", sa.String(100), nullable=False),
        sa.UniqueConstraint(
            "execution_id", "ordinal", name="uq_job_attempts_execution_ordinal"
        ),
        sa.CheckConstraint("ordinal >= 1", name="ck_job_attempts_ordinal"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_job_attempts_duration",
        ),
    )
    op.create_index(
        "ix_job_attempts_correlation_started",
        "job_attempts",
        ["correlation_id", "started_at"],
    )

    op.create_table(
        "job_outbox_messages",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "execution_id",
            _uuid(),
            sa.ForeignKey("job_executions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False),
        sa.Column("state", _enum("job_outbox_state"), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "execution_id", "attempt_number", name="uq_job_outbox_execution_attempt"
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_job_outbox_attempt_number"
        ),
        sa.CheckConstraint(
            "publish_attempts >= 0 AND publish_attempts <= 100",
            name="ck_job_outbox_publish_attempts",
        ),
    )
    op.create_index(
        "ix_job_outbox_state_available",
        "job_outbox_messages",
        ["state", "available_at"],
    )

    op.create_table(
        "job_schedules",
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("logical_target", sa.String(300), nullable=False),
        sa.Column("schedule_kind", _enum("schedule_kind"), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("max_attempts", sa.SmallInteger(), nullable=False),
        sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", _uuid(), primary_key=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(schedule_kind = 'fixed_interval' AND interval_seconds >= 60) OR "
            "schedule_kind = 'one_shot'",
            name="ck_job_schedules_interval",
        ),
        sa.CheckConstraint(
            "schedule_kind IN ('one_shot', 'fixed_interval')",
            name="ck_job_schedules_kind",
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_job_schedules_max_attempts",
        ),
    )
    op.create_index(
        "ix_job_schedules_due", "job_schedules", ["enabled", "next_run_at"]
    )

    op.create_table(
        "stored_objects",
        sa.Column("purpose", sa.String(100), nullable=False),
        sa.Column("id", _uuid(), primary_key=True),
        *_timestamps(),
        sa.CheckConstraint(
            "length(purpose) BETWEEN 1 AND 100",
            name="ck_stored_objects_purpose",
        ),
    )

    op.create_table(
        "stored_object_versions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "object_id",
            _uuid(),
            sa.ForeignKey("stored_objects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", _enum("object_version_state"), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("provider_version", sa.String(300), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_kind", _enum("actor_kind"), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.UniqueConstraint(
            "storage_key", name="uq_stored_object_versions_storage_key"
        ),
        sa.CheckConstraint(
            "size_bytes >= 0", name="ck_stored_object_versions_size"
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_stored_object_versions_sha256",
        ),
        sa.CheckConstraint(
            "(state = 'available' AND available_at IS NOT NULL) OR "
            "(state <> 'available' AND available_at IS NULL)",
            name="ck_stored_object_versions_available_at",
        ),
    )
    op.create_index(
        "ix_stored_object_versions_object_created",
        "stored_object_versions",
        ["object_id", "created_at"],
    )
    op.create_index(
        "ix_stored_object_versions_state_created",
        "stored_object_versions",
        ["state", "created_at"],
    )
    op.create_index(
        "ix_stored_object_versions_correlation",
        "stored_object_versions",
        ["correlation_id"],
    )

    op.create_table(
        "runtime_surface_status",
        sa.Column("environment", _enum("runtime_environment"), primary_key=True),
        sa.Column("surface", _enum("runtime_surface"), primary_key=True),
        sa.Column("release_id", sa.String(100), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_digest", sa.String(200), nullable=False),
        sa.Column("state", _enum("runtime_surface_state"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checks", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.CheckConstraint(
            "environment IN ('local', 'preview', 'production')",
            name="ck_runtime_surface_environment",
        ),
        sa.CheckConstraint(
            "surface IN ('web', 'api', 'worker', 'scheduler')",
            name="ck_runtime_surface_surface",
        ),
        sa.CheckConstraint(
            "state IN ('ready', 'degraded', 'not_ready')",
            name="ck_runtime_surface_state",
        ),
    )
    op.create_index(
        "ix_runtime_surface_observed", "runtime_surface_status", ["observed_at"]
    )
    verify_bootstrap(bind)


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = inspect(bind)
    except NoInspectionAvailable:
        # Offline SQL generation cannot inspect or count rows; emit the
        # declared empty-only operations and let the live run enforce safety.
        for table_name in reversed(TABLE_SNAPSHOT):
            op.drop_table(table_name)
        for enum_name in reversed(tuple(_ENUM_VALUES)):
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")
        return

    existing = set(inspector.get_table_names())
    for table_name in TABLE_SNAPSHOT:
        if table_name in existing:
            if bind.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1")).first():
                raise RuntimeError("foundation downgrade requires empty tables")
    for table_name in reversed(TABLE_SNAPSHOT):
        if table_name in existing:
            op.drop_table(table_name)
    for enum_name in reversed(tuple(_ENUM_VALUES)):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")


def verify_bootstrap(bind: Any) -> bool:
    """Verify tables, extensions, enum domains and named constraints."""

    if bind is None:
        return False
    try:
        inspector = inspect(bind)
    except NoInspectionAvailable:
        return True
    tables_ok = set(TABLE_SNAPSHOT).issubset(set(inspector.get_table_names()))
    extensions = {
        str(row[0])
        for row in bind.execute(
            text(
                "SELECT extname FROM pg_extension "
                "WHERE extname IN ('postgis', 'vector')"
            )
        )
    }
    enum_names = ", ".join(f"'{name}'" for name in sorted(ENUM_SNAPSHOT))
    enums = {
        str(row[0])
        for row in bind.execute(
            text(
                "SELECT typname FROM pg_type WHERE typtype = 'e' "
                f"AND typname IN ({enum_names})"
            )
        )
    }
    constraint_names = ", ".join(
        f"'{name}'"
        for name in sorted(name for name in CONSTRAINT_SNAPSHOT if not name.startswith("ix_"))
    )
    constraints = {
        str(row[0])
        for row in bind.execute(
            text(
                "SELECT conname FROM pg_constraint "
                f"WHERE conname IN ({constraint_names})"
            )
        )
    }
    index_names = ", ".join(f"'{name}'" for name in sorted(INDEX_SNAPSHOT))
    indexes = {
        str(row[0])
        for row in bind.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                f"WHERE indexname IN ({index_names})"
            )
        )
    }
    return (
        tables_ok
        and set(REQUIRED_EXTENSIONS).issubset(extensions)
        and set(ENUM_SNAPSHOT).issubset(enums)
        and set(name for name in CONSTRAINT_SNAPSHOT if not name.startswith("ix_"))
        .issubset(constraints)
        and INDEX_SNAPSHOT.issubset(indexes)
    )
