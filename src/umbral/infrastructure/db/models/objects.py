"""Logical stored object and immutable version mappings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin


class StoredObject(IdentityAuditMixin, Base):
    __tablename__ = "stored_objects"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "length(purpose) BETWEEN 1 AND 100", name="ck_stored_objects_purpose"
        ),
    )

    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    versions: Mapped[list[StoredObjectVersion]] = relationship(back_populates="object")


class StoredObjectVersion(Base):
    __tablename__ = "stored_object_versions"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_stored_object_versions_storage_key"),
        CheckConstraint("size_bytes >= 0", name="ck_stored_object_versions_size"),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_stored_object_versions_sha256",
        ),
        CheckConstraint(
            "(state = 'available' AND available_at IS NOT NULL) OR "
            "(state <> 'available' AND available_at IS NULL)",
            name="ck_stored_object_versions_available_at",
        ),
        Index("ix_stored_object_versions_object_created", "object_id", "created_at"),
        Index("ix_stored_object_versions_state_created", "state", "created_at"),
        Index("ix_stored_object_versions_correlation", "correlation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    object_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("stored_objects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    provider_version: Mapped[str | None] = mapped_column(String(300), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    object: Mapped[StoredObject] = relationship(back_populates="versions")
