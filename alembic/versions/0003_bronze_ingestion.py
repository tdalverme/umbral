"""Bronze ingestion schema: import runs, raw snapshots and quarantine."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_bronze_ingestion"
down_revision = "0002_private_beta_identity"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "import_format": ("csv", "json"),
        "import_run_state": ("pending", "running", "succeeded", "failed"),
    }[name]
    return postgresql.ENUM(*values, name=name, create_type=False)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind", _enum("actor_kind"), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _create_types() -> None:
    op.execute("CREATE TYPE import_format AS ENUM ('csv', 'json')")
    op.execute(
        "CREATE TYPE import_run_state AS ENUM "
        "('pending', 'running', 'succeeded', 'failed')"
    )


def upgrade() -> None:
    _create_types()

    op.create_table(
        "import_runs",
        *_audit_columns(),
        sa.Column("job_execution_id", _uuid()),
        sa.Column("batch_key", sa.String(200), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_version", sa.String(100), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("file_format", _enum("import_format"), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("raw_storage_key", sa.String(500), nullable=False),
        sa.Column("state", _enum("import_run_state"), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quarantined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_fields", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finished_at", _ts()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_detail", sa.String(500)),
        sa.UniqueConstraint(
            "source_id", "batch_key", name="uq_import_runs_source_batch"
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_import_runs_state",
        ),
        sa.CheckConstraint(
            "(state IN ('succeeded', 'failed') AND finished_at IS NOT NULL) OR "
            "(state NOT IN ('succeeded', 'failed') AND finished_at IS NULL)",
            name="ck_import_runs_terminal_finished",
        ),
        sa.CheckConstraint(
            "total_records >= 0 AND accepted >= 0 AND quarantined >= 0 "
            "AND duplicates >= 0 AND missing_fields >= 0",
            name="ck_import_runs_counts",
        ),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_import_runs_file_size"),
    )
    op.create_foreign_key(
        "fk_import_runs_job_execution",
        "import_runs",
        "job_executions",
        ["job_execution_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_import_runs_state_created", "import_runs", ["state", "created_at"]
    )
    op.create_index("ix_import_runs_correlation", "import_runs", ["correlation_id"])

    op.create_table(
        "raw_listing_snapshots",
        *_audit_columns(),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("import_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_version", sa.String(100), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("published_at", _ts()),
        sa.Column("captured_at", _ts(), nullable=False),
        sa.UniqueConstraint(
            "source_id",
            "external_id",
            "content_sha256",
            name="uq_raw_listing_snapshots_content",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_raw_listing_snapshots_size"),
    )
    op.create_index("ix_raw_listing_snapshots_run", "raw_listing_snapshots", ["run_id"])
    op.create_index(
        "ix_raw_listing_snapshots_source_external",
        "raw_listing_snapshots",
        ["source_id", "external_id"],
    )

    op.create_table(
        "quarantine_records",
        *_audit_columns(),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("import_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_version", sa.String(100), nullable=False),
        sa.Column("contract_version", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(500)),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("rule", sa.String(100), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.CheckConstraint(
            "length(detail) <= 500", name="ck_quarantine_records_detail"
        ),
    )
    op.create_index("ix_quarantine_records_run", "quarantine_records", ["run_id"])
    op.create_index("ix_quarantine_records_code", "quarantine_records", ["code"])


def downgrade() -> None:
    op.drop_table("quarantine_records")
    op.drop_table("raw_listing_snapshots")
    op.drop_table("import_runs")
    op.execute("DROP TYPE IF EXISTS import_run_state")
    op.execute("DROP TYPE IF EXISTS import_format")
