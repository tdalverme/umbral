"""Transport-independent values and errors for immutable object versions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol
from uuid import UUID

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ObjectError(RuntimeError):
    """Base class for sanitized object-storage failures."""

    code = "object.error"


class ObjectVersionConflict(ObjectError):
    """The immutable version already exists with different properties."""

    code = "object.version_conflict"


class ObjectIntegrityError(ObjectError):
    """Declared or provider bytes failed hash/size validation."""

    code = "object.integrity_error"


class ObjectNotFound(ObjectError):
    """An exact version or provider object is unavailable."""

    code = "object.not_found"


class ObjectStateError(ObjectError):
    """A version is not in a valid state for the requested operation."""

    code = "object.invalid_state"


@dataclass(frozen=True, slots=True)
class ObjectVersionRef:
    """Stable application reference to one exact, available version."""

    object_id: UUID
    version_id: UUID
    sha256: str
    size_bytes: int
    content_type: str

    def __post_init__(self) -> None:
        digest = self.sha256.lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("sha256 must be lowercase hexadecimal")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        media_type = self.content_type.strip().lower()
        if not media_type or ";" in media_type:
            raise ValueError("content_type must be a normalized media type")
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "content_type", media_type)


@dataclass(frozen=True, slots=True, repr=False)
class ProviderObjectRef:
    """Opaque adapter reference; its provider key is never exposed by repr."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("provider reference must not be empty")

    def __repr__(self) -> str:
        return "ProviderObjectRef(<opaque>)"


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """Verified metadata returned by an object adapter."""

    provider_ref: ProviderObjectRef
    sha256: str
    size_bytes: int
    content_type: str
    provider_version: str | None = None

    def __post_init__(self) -> None:
        digest = self.sha256.lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("sha256 must be lowercase hexadecimal")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if ";" in self.content_type:
            raise ValueError("content_type must be a normalized media type")
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "content_type", self.content_type.strip().lower())


@dataclass(slots=True)
class ObjectVersionMetadata:
    """Repository record used while bytes cross the DB/provider boundary."""

    object_id: UUID
    version_id: UUID
    purpose: str
    state: str
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str
    created_at: datetime
    correlation_id: UUID
    provider_ref: ProviderObjectRef | None = None
    provider_version: str | None = None
    available_at: datetime | None = None
    failure_code: str | None = None

    def ref(self) -> ObjectVersionRef:
        return ObjectVersionRef(
            object_id=self.object_id,
            version_id=self.version_id,
            sha256=self.sha256,
            size_bytes=self.size_bytes,
            content_type=self.content_type,
        )


class ObjectStore(Protocol):
    """Provider-neutral immutable object adapter contract."""

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


class VersionedObjects(Protocol):
    """Deep module exposing exact available application versions."""

    def put(self, **kwargs: object) -> ObjectVersionRef: ...

    def open(self, ref: ObjectVersionRef) -> BinaryIO: ...

    def stat(self, ref: ObjectVersionRef) -> ObjectInfo: ...
