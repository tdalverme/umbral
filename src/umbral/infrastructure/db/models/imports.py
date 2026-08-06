"""Bronze ingestion: import runs, raw snapshots and quarantine mappings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

IMPORT_FORMAT = ENUM(
    "csv",
    "json",
    name="import_format",
    create_type=True,
)
IMPORT_RUN_STATE = ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    name="import_run_state",
    create_type=True,
)


class ImportRun(IdentityAuditMixin, Base):
    __tablename__ = "import_runs"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("source_id", "batch_key", name="uq_import_runs_source_batch"),
        CheckConstraint(
            "state IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_import_runs_state",
        ),
        CheckConstraint(
            "(state IN ('succeeded', 'failed') AND finished_at IS NOT NULL) OR "
            "(state NOT IN ('succeeded', 'failed') AND finished_at IS NULL)",
            name="ck_import_runs_terminal_finished",
        ),
        CheckConstraint(
            "total_records >= 0 AND accepted >= 0 AND quarantined >= 0 "
            "AND duplicates >= 0 AND missing_fields >= 0",
            name="ck_import_runs_counts",
        ),
        CheckConstraint("file_size_bytes >= 0", name="ck_import_runs_file_size"),
        Index("ix_import_runs_state_created", "state", "created_at"),
        Index("ix_import_runs_correlation", "correlation_id"),
    )

    job_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("job_executions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    batch_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    file_format: Mapped[str] = mapped_column(
        IMPORT_FORMAT, nullable=False, default="json"
    )
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(
        IMPORT_RUN_STATE, nullable=False, default="pending"
    )
    total_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_fields: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RawListingSnapshot(IdentityAuditMixin, Base):
    __tablename__ = "raw_listing_snapshots"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_id",
            "content_sha256",
            name="uq_raw_listing_snapshots_content",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_raw_listing_snapshots_size"),
        Index("ix_raw_listing_snapshots_run", "run_id"),
        Index("ix_raw_listing_snapshots_source_external", "source_id", "external_id"),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class QuarantineRecord(IdentityAuditMixin, Base):
    __tablename__ = "quarantine_records"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint("length(detail) <= 500", name="ck_quarantine_records_detail"),
        Index("ix_quarantine_records_run", "run_id"),
        Index("ix_quarantine_records_code", "code"),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
