"""Small application seams for versioned object storage."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID

from umbral.application.objects.contracts import (
    ObjectInfo,
    ObjectVersionMetadata,
    ObjectVersionRef,
    ProviderObjectRef,
)


class ObjectStore(Protocol):
    """Provider-neutral immutable object adapter."""

    def put_if_absent(
        self,
        *,
        storage_key: str,
        body: BinaryIO,
        sha256: str,
        size_bytes: int,
        content_type: str,
    ) -> ProviderObjectRef: ...

    def open(self, provider_ref: ProviderObjectRef) -> BinaryIO: ...

    def stat(self, provider_ref: ProviderObjectRef) -> ObjectInfo: ...

    def ref_for_key(self, storage_key: str) -> ProviderObjectRef: ...


class ObjectMetadataRepository(Protocol):
    """Persistence seam; implementations never commit transactions."""

    def get(
        self, object_id: UUID, version_id: UUID
    ) -> ObjectVersionMetadata | None: ...

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
    ) -> ObjectVersionMetadata: ...

    def mark_available(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        provider_ref: ProviderObjectRef,
        provider_version: str | None,
        available_at: datetime,
    ) -> ObjectVersionMetadata: ...

    def mark_failed(
        self,
        *,
        object_id: UUID,
        version_id: UUID,
        failure_code: str,
    ) -> ObjectVersionMetadata: ...

    def pending(
        self, *, before: datetime | None = None
    ) -> Iterator[ObjectVersionMetadata]: ...

    def provider_ref_for(self, storage_key: str) -> ProviderObjectRef: ...


class VersionedObjects(Protocol):
    """Deep module exposing only exact available application versions."""

    def put(self, **kwargs: object) -> ObjectVersionRef: ...

    def open(self, ref: ObjectVersionRef) -> BinaryIO: ...

    def stat(self, ref: ObjectVersionRef) -> ObjectInfo: ...


Clock = Callable[[], datetime]
ObjectStoreRoot = Path
