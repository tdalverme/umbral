"""SQLAlchemy repository for versioned object metadata (no commit methods)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.objects.contracts import (
    ObjectVersionConflict,
    ObjectVersionMetadata,
    ProviderObjectRef,
)
from umbral.infrastructure.db.models.objects import StoredObject, StoredObjectVersion


class SqlAlchemyObjectRepository:
    """Persistence adapter scoped to a caller-owned SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, object_id: UUID, version_id: UUID) -> ObjectVersionMetadata | None:
        row = self.session.get(StoredObjectVersion, version_id)
        if row is None or row.object_id != object_id:
            return None
        return self._to_metadata(row)

    def create_pending(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        purpose: str,
        storage_key: str,
        sha256: str,
        size_bytes: int,
        content_type: str,
        created_at: datetime,
        correlation_id: UUID,
    ) -> ObjectVersionMetadata:
        existing = self.get(object_id, version_id)
        if existing is not None:
            if (
                existing.sha256 != sha256
                or existing.size_bytes != size_bytes
                or existing.content_type != content_type
            ):
                raise ObjectVersionConflict("immutable application version conflicts")
            return existing
        logical = self.session.get(StoredObject, object_id)
        if logical is None:
            logical = StoredObject(
                id=object_id,
                purpose=purpose,
                created_at=created_at,
                updated_at=created_at,
                version=1,
                actor_kind="system",
                source="object_service",
                correlation_id=correlation_id,
            )
            self.session.add(logical)
        elif logical.purpose != purpose:
            raise ObjectVersionConflict("logical object purpose conflicts")
        row = StoredObjectVersion(
            id=version_id,
            object_id=object_id,
            state="pending",
            storage_key=storage_key,
            sha256=sha256,
            size_bytes=size_bytes,
            content_type=content_type,
            created_at=created_at,
            actor_kind="system",
            source="object_service",
            correlation_id=correlation_id,
        )
        self.session.add(row)
        self.session.flush()
        return self._to_metadata(row)

    def mark_available(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        provider_ref: ProviderObjectRef,
        provider_version: str | None,
        available_at: datetime,
    ) -> ObjectVersionMetadata:
        row = self._require(object_id, version_id)
        if row.state == "available":
            return self._to_metadata(row)
        if row.state != "pending":
            raise ObjectVersionConflict("only pending versions can become available")
        row.state = "available"
        row.provider_version = provider_version or provider_ref.value
        row.available_at = available_at
        self.session.flush()
        return self._to_metadata(row)

    def mark_failed(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        failure_code: str,
    ) -> ObjectVersionMetadata:
        row = self._require(object_id, version_id)
        if row.state != "available":
            row.state = "failed"
            row.failure_code = failure_code[:100]
            row.available_at = None
            self.session.flush()
        return self._to_metadata(row)

    def pending(
        self, *, before: datetime | None = None
    ) -> Iterator[ObjectVersionMetadata]:
        statement = select(StoredObjectVersion).where(
            StoredObjectVersion.state == "pending"
        )
        if before is not None:
            statement = statement.where(StoredObjectVersion.created_at < before)
        for row in self.session.scalars(statement):
            yield self._to_metadata(row)

    def provider_ref_for(self, storage_key: str) -> ProviderObjectRef:
        return ProviderObjectRef(storage_key)

    def _require(self, object_id: UUID, version_id: UUID) -> StoredObjectVersion:
        row = self.session.get(StoredObjectVersion, version_id)
        if row is None or row.object_id != object_id:
            raise KeyError("object version metadata is unavailable")
        return row

    def _to_metadata(self, row: StoredObjectVersion) -> ObjectVersionMetadata:
        logical = self.session.get(StoredObject, row.object_id)
        purpose = logical.purpose if logical is not None else "runtime_reference"
        return _to_metadata(row, purpose=purpose)


def _to_metadata(
    row: StoredObjectVersion, *, purpose: str = "runtime_reference"
) -> ObjectVersionMetadata:
    provider_ref = (
        ProviderObjectRef(row.provider_version) if row.provider_version else None
    )
    return ObjectVersionMetadata(
        object_id=row.object_id,
        version_id=row.id,
        purpose=purpose,
        state=str(row.state),
        storage_key=row.storage_key,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        content_type=row.content_type,
        created_at=row.created_at,
        correlation_id=row.correlation_id,
        provider_ref=provider_ref,
        provider_version=row.provider_version,
        available_at=row.available_at,
        failure_code=row.failure_code,
    )
