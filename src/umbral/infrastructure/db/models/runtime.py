"""Operational surface heartbeat mapping."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base

RUNTIME_ENVIRONMENT = ENUM(
    "local",
    "preview",
    "production",
    name="runtime_environment",
    create_type=True,
)
RUNTIME_SURFACE = ENUM(
    "web",
    "api",
    "worker",
    "scheduler",
    name="runtime_surface",
    create_type=True,
)
RUNTIME_SURFACE_STATE = ENUM(
    "ready",
    "degraded",
    "not_ready",
    name="runtime_surface_state",
    create_type=True,
)


class RuntimeSurfaceStatus(Base):
    __tablename__ = "runtime_surface_status"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('local', 'preview', 'production')",
            name="ck_runtime_surface_environment",
        ),
        CheckConstraint(
            "surface IN ('web', 'api', 'worker', 'scheduler')",
            name="ck_runtime_surface_surface",
        ),
        CheckConstraint(
            "state IN ('ready', 'degraded', 'not_ready')",
            name="ck_runtime_surface_state",
        ),
        Index("ix_runtime_surface_observed", "observed_at"),
    )

    environment: Mapped[str] = mapped_column(RUNTIME_ENVIRONMENT, primary_key=True)
    surface: Mapped[str] = mapped_column(RUNTIME_SURFACE, primary_key=True)
    release_id: Mapped[str] = mapped_column(String(100), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(RUNTIME_SURFACE_STATE, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    checks: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
