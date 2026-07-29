"""Foundation runtime PostgreSQL bootstrap; empty-only downgrade.

The revision is intentionally linear and transactional.  Downgrade is a
declared empty-database escape hatch only; later releases compensate forward.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from alembic import op
from sqlalchemy import inspect, text

from umbral.infrastructure.db.migrations import expected_schema

revision = "0001_foundation_runtime"
down_revision = None
branch_labels = None
depends_on = None

EXPECTED_TABLES = (
    "job_executions",
    "job_attempts",
    "job_outbox_messages",
    "job_schedules",
    "stored_objects",
    "stored_object_versions",
    "runtime_surface_status",
)
REQUIRED_EXTENSIONS = ("postgis", "vector")
TRANSACTIONAL = True
DOWNGRADE_POLICY = "empty-only"


def _table_names() -> set[str]:
    return set(expected_schema().tables)


def upgrade() -> None:
    bind = op.get_bind()
    for extension in REQUIRED_EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
    metadata = expected_schema()
    # Metadata is imported only in the migration layer; application startup
    # never invokes this function.
    for table in metadata.sorted_tables:
        table.create(bind=bind, checkfirst=False)
    verify_bootstrap(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    foundation = set(EXPECTED_TABLES)
    if existing.intersection(foundation):
        rows = bind.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(:tables)"
            ),
            {"tables": list(existing.intersection(foundation))},
        )
        non_empty: list[str] = []
        for row in rows:
            table_name = str(row[0])
            if bind.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1")).first() is not None:
                non_empty.append(table_name)
        if non_empty:
            raise RuntimeError("foundation downgrade requires empty tables")
    for table_name in reversed(EXPECTED_TABLES):
        if table_name in existing:
            op.drop_table(table_name)


def verify_bootstrap(bind: Any) -> bool:
    """Verify table inventory without leaking connection details."""

    if bind is None:
        return False
    inspector = inspect(bind)
    return _table_names().issubset(set(inspector.get_table_names()))
