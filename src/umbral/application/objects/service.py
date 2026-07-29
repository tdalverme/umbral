"""Recoverable metadata/bytes coordination for immutable object versions."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import BinaryIO
from uuid import UUID, uuid4

from umbral.application.objects.contracts import (
    ObjectInfo,
    ObjectIntegrityError,
    ObjectNotFound,
    ObjectStateError,
    ObjectVersionConflict,
    ObjectVersionMetadata,
    ObjectVersionRef,
    ProviderObjectRef,
)
from umbral.application.objects.ports import (
    Clock,
    ObjectMetadataRepository,
    ObjectStore,
)
from umbral.application.runtime.telemetry import Environment, TelemetrySignal


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Bounded outcome of one pending-write reconciliation pass."""

    completed: int = 0
    failed: int = 0
    pending: int = 0


class InMemoryObjectMetadataRepository:
    """Deterministic repository used by local/contract tests.

    Production callers can provide the SQLAlchemy repository without changing
    the service or object-store seam.
    """

    def __init__(self) -> None:
        self._versions: dict[tuple[UUID, UUID], ObjectVersionMetadata] = {}

    def get(self, object_id: UUID, version_id: UUID) -> ObjectVersionMetadata | None:
        return self._versions.get((object_id, version_id))

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
        key = (object_id, version_id)
        existing = self._versions.get(key)
        if existing is not None:
            if (
                existing.sha256 != sha256
                or existing.size_bytes != size_bytes
                or existing.content_type != content_type
            ):
                raise ObjectVersionConflict("immutable application version conflicts")
            return existing
        metadata = ObjectVersionMetadata(
            object_id=object_id,
            version_id=version_id,
            purpose=purpose,
            state="pending",
            storage_key=storage_key,
            sha256=sha256,
            size_bytes=size_bytes,
            content_type=content_type,
            created_at=created_at,
            correlation_id=correlation_id,
        )
        self._versions[key] = metadata
        return metadata

    def mark_available(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        provider_ref: ProviderObjectRef,
        provider_version: str | None,
        available_at: datetime,
    ) -> ObjectVersionMetadata:
        metadata = self._require(object_id, version_id)
        if metadata.state == "available":
            if metadata.provider_ref != provider_ref:
                raise ObjectVersionConflict("available provider reference conflicts")
            return metadata
        if metadata.state != "pending":
            raise ObjectStateError("only pending versions can become available")
        metadata.state = "available"
        metadata.provider_ref = provider_ref
        metadata.provider_version = provider_version
        metadata.available_at = available_at
        return metadata

    def mark_failed(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        failure_code: str,
    ) -> ObjectVersionMetadata:
        metadata = self._require(object_id, version_id)
        if metadata.state == "available":
            return metadata
        metadata.state = "failed"
        metadata.failure_code = _safe_failure_code(failure_code)
        metadata.provider_ref = None
        metadata.available_at = None
        return metadata

    def pending(
        self, *, before: datetime | None = None
    ) -> Iterator[ObjectVersionMetadata]:
        for metadata in tuple(self._versions.values()):
            if metadata.state != "pending":
                continue
            if before is not None and metadata.created_at >= before:
                continue
            yield metadata

    def provider_ref_for(self, storage_key: str) -> ProviderObjectRef:
        # The in-memory repository cannot resolve a provider key itself. The
        # service asks the adapter to do so and uses this deterministic token as
        # a fallback for adapters that expose key-shaped refs.
        return ProviderObjectRef(storage_key)

    def ref(self, object_id: UUID, version_id: UUID) -> ObjectVersionRef:
        return self._require(object_id, version_id).ref()

    def _require(self, object_id: UUID, version_id: UUID) -> ObjectVersionMetadata:
        try:
            return self._versions[(object_id, version_id)]
        except KeyError as error:
            raise ObjectNotFound("object version metadata is unavailable") from error


class VersionedObjects:
    """Deep module coordinating pending metadata and immutable provider bytes."""

    def __init__(
        self,
        store: ObjectStore,
        *,
        repository: ObjectMetadataRepository | None = None,
        clock: Clock | None = None,
        release_id: str = "foundation-local",
        environment: Environment = "local",
    ) -> None:
        self.store = store
        self.repository = repository or InMemoryObjectMetadataRepository()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.release_id = release_id
        self.environment = environment
        self.signals: list[TelemetrySignal] = []

    def put(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        body: BinaryIO | bytes,
        sha256: str | None = None,
        size_bytes: int | None = None,
        content_type: str = "application/octet-stream",
        purpose: str = "runtime_reference",
        correlation_id: UUID | None = None,
    ) -> ObjectVersionRef:
        raw = body if isinstance(body, bytes) else body.read()
        if not isinstance(raw, bytes):
            raise ObjectIntegrityError("object body did not return bytes")
        actual_digest = hashlib.sha256(raw).hexdigest()
        actual_size = len(raw)
        declared_digest = (sha256 or actual_digest).lower()
        declared_size = actual_size if size_bytes is None else size_bytes
        media_type = _normalize_content_type(content_type)
        existing = self.repository.get(object_id, version_id)
        if existing is not None:
            _ensure_metadata_match(existing, declared_digest, declared_size, media_type)
            if declared_digest != actual_digest or declared_size != actual_size:
                raise ObjectVersionConflict("immutable application version conflicts")
            if existing.state == "available":
                return existing.ref()
            if existing.state == "failed":
                raise ObjectStateError(
                    "failed object versions are not implicitly retried"
                )

        if declared_digest != actual_digest or declared_size != actual_size:
            raise ObjectIntegrityError("declared object integrity does not match bytes")

        key = f"objects/{object_id}/{version_id}"
        self.repository.create_pending(
            object_id=object_id,
            version_id=version_id,
            purpose=purpose,
            storage_key=key,
            sha256=declared_digest,
            size_bytes=declared_size,
            content_type=media_type,
            created_at=self.clock(),
            correlation_id=correlation_id or uuid4(),
        )
        try:
            provider_ref = self.store.put_if_absent(
                storage_key=key,
                body=BytesIO(raw),
                sha256=declared_digest,
                size_bytes=declared_size,
                content_type=media_type,
            )
            info = self.store.stat(provider_ref)
            _ensure_info_match(info, declared_digest, declared_size, media_type)
        except Exception as error:
            if not isinstance(error, ObjectVersionConflict):
                self.repository.mark_failed(
                    object_id=object_id,
                    version_id=version_id,
                    failure_code=getattr(error, "code", "object.write_failed"),
                )
            raise
        metadata = self.repository.mark_available(
            object_id=object_id,
            version_id=version_id,
            provider_ref=provider_ref,
            provider_version=info.provider_version,
            available_at=self.clock(),
        )
        self.signals.append(
            TelemetrySignal(
                correlation_id=str(metadata.correlation_id),
                service_name="worker",
                environment=self.environment,
                release_id=self.release_id,
                operation="object.put",
                state="available",
                duration_ms=0,
                object_operation="put",
            )
        )
        return metadata.ref()

    def open(self, ref: ObjectVersionRef) -> BinaryIO:
        metadata = self._available(ref)
        if metadata.provider_ref is None:
            raise ObjectIntegrityError("available object has no provider reference")
        info = self.store.stat(metadata.provider_ref)
        _ensure_info_match(info, ref.sha256, ref.size_bytes, ref.content_type)
        return self.store.open(metadata.provider_ref)

    def stat(self, ref: ObjectVersionRef) -> ObjectInfo:
        metadata = self._available(ref)
        if metadata.provider_ref is None:
            raise ObjectIntegrityError("available object has no provider reference")
        info = self.store.stat(metadata.provider_ref)
        _ensure_info_match(info, ref.sha256, ref.size_bytes, ref.content_type)
        return info

    def reconcile_pending(
        self,
        *,
        max_age: timedelta | None = None,
    ) -> ReconciliationResult:
        now = self.clock()
        before = now - max_age if max_age is not None else None
        completed = failed = pending = 0
        for metadata in self.repository.pending(before=before):
            provider_ref = metadata.provider_ref
            if provider_ref is None:
                provider_ref = _adapter_ref_for_key(self.store, metadata.storage_key)
            try:
                info = self.store.stat(provider_ref)
                _ensure_info_match(
                    info, metadata.sha256, metadata.size_bytes, metadata.content_type
                )
            except ObjectNotFound:
                if max_age is not None and now - metadata.created_at >= max_age:
                    self.repository.mark_failed(
                        object_id=metadata.object_id,
                        version_id=metadata.version_id,
                        failure_code="object.bytes_missing",
                    )
                    failed += 1
                else:
                    pending += 1
                continue
            except (ObjectIntegrityError, ObjectVersionConflict):
                self.repository.mark_failed(
                    object_id=metadata.object_id,
                    version_id=metadata.version_id,
                    failure_code="object.bytes_conflict",
                )
                failed += 1
                continue
            self.repository.mark_available(
                object_id=metadata.object_id,
                version_id=metadata.version_id,
                provider_ref=provider_ref,
                provider_version=info.provider_version,
                available_at=now,
            )
            completed += 1
        return ReconciliationResult(completed, failed, pending)

    def _available(self, ref: ObjectVersionRef) -> ObjectVersionMetadata:
        metadata = self.repository.get(ref.object_id, ref.version_id)
        if metadata is None or metadata.state != "available":
            raise ObjectNotFound("exact object version is not available")
        _ensure_metadata_match(metadata, ref.sha256, ref.size_bytes, ref.content_type)
        return metadata


def _adapter_ref_for_key(store: ObjectStore, storage_key: str) -> ProviderObjectRef:
    resolver = getattr(store, "ref_for_key", None)
    if callable(resolver):
        result = resolver(storage_key)
        if not isinstance(result, ProviderObjectRef):
            raise ObjectIntegrityError(
                "provider reference resolver returned invalid data"
            )
        return result
    return ProviderObjectRef(storage_key)


def _ensure_metadata_match(
    metadata: ObjectVersionMetadata, digest: str, size: int, content_type: str
) -> None:
    if (
        metadata.sha256 != digest
        or metadata.size_bytes != size
        or metadata.content_type != content_type
    ):
        raise ObjectVersionConflict("immutable application version conflicts")


def _ensure_info_match(
    info: ObjectInfo, digest: str, size: int, content_type: str
) -> None:
    if (
        info.sha256 != digest
        or info.size_bytes != size
        or info.content_type != content_type
    ):
        raise ObjectIntegrityError(
            "provider metadata does not match application version"
        )


def _normalize_content_type(value: str) -> str:
    media_type = value.strip().lower()
    if ";" in media_type or "/" not in media_type:
        raise ValueError("content_type must be a normalized media type")
    return media_type


def _safe_failure_code(value: str) -> str:
    candidate = value.lower().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789._-"
    if not candidate or any(char not in allowed for char in candidate):
        return "object.write_failed"
    return candidate[:100]
