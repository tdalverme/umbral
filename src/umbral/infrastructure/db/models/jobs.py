"""Durable job, attempt, outbox and schedule mappings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin


class JobExecution(IdentityAuditMixin, Base):
    __tablename__ = "job_executions"
    __table_args__ = (
        UniqueConstraint(
            "job_type",
            "logical_target",
            "idempotency_key",
            name="uq_job_executions_identity",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_job_executions_attempt_bounds",
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 10",
            name="ck_job_executions_max_attempts",
        ),
        CheckConstraint(
            "(state IN ('succeeded', 'failed') AND finished_at IS NOT NULL) OR "
            "(state NOT IN ('succeeded', 'failed') AND finished_at IS NULL)",
            name="ck_job_executions_terminal_finished",
        ),
        CheckConstraint(
            "(state = 'running' AND lease_owner IS NOT NULL "
            "AND lease_until IS NOT NULL) OR "
            "(state <> 'running' OR (lease_owner IS NULL AND lease_until IS NULL))",
            name="ck_job_executions_running_lease",
        ),
        Index("ix_job_executions_state_available", "state", "available_at"),
        Index("ix_job_executions_state_lease", "state", "lease_until"),
        Index("ix_job_executions_correlation", "correlation_id"),
    )

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    logical_target: Mapped[str] = mapped_column(String(300), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attempts: Mapped[list[JobAttempt]] = relationship(back_populates="execution")
    outbox_messages: Mapped[list[JobOutboxMessage]] = relationship(
        back_populates="execution"
    )


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        UniqueConstraint(
            "execution_id", "ordinal", name="uq_job_attempts_execution_ordinal"
        ),
        CheckConstraint("ordinal >= 1", name="ck_job_attempts_ordinal"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_job_attempts_duration"
        ),
        Index("ix_job_attempts_correlation_started", "correlation_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("job_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    transport_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    release_id: Mapped[str] = mapped_column(String(100), nullable=False)

    execution: Mapped[JobExecution] = relationship(back_populates="attempts")


class JobOutboxMessage(Base):
    __tablename__ = "job_outbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "execution_id", "attempt_number", name="uq_job_outbox_execution_attempt"
        ),
        CheckConstraint("attempt_number >= 1", name="ck_job_outbox_attempt_number"),
        CheckConstraint(
            "publish_attempts >= 0 AND publish_attempts <= 100",
            name="ck_job_outbox_publish_attempts",
        ),
        Index("ix_job_outbox_state_available", "state", "available_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("job_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    publish_attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    execution: Mapped[JobExecution] = relationship(back_populates="outbox_messages")


class JobSchedule(IdentityAuditMixin, Base):
    __tablename__ = "job_schedules"
    __table_args__ = (
        CheckConstraint(
            "schedule_kind IN ('one_shot', 'fixed_interval')",
            name="ck_job_schedules_kind",
        ),
        CheckConstraint(
            "(schedule_kind = 'fixed_interval' AND interval_seconds >= 60) OR "
            "schedule_kind = 'one_shot'",
            name="ck_job_schedules_interval",
        ),
        CheckConstraint(
            "max_attempts BETWEEN 1 AND 10", name="ck_job_schedules_max_attempts"
        ),
        Index("ix_job_schedules_due", "enabled", "next_run_at"),
    )

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    logical_target: Mapped[str] = mapped_column(String(300), nullable=False)
    schedule_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    last_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
