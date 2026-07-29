"""Versioned object metadata state-machine tests (T059)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from umbral.application.objects.contracts import (
    ObjectIntegrityError,
    ObjectNotFound,
    ObjectVersionConflict,
)
from umbral.application.objects.service import (
    InMemoryObjectMetadataRepository,
    VersionedObjects,
)
from umbral.infrastructure.object_store.filesystem import FilesystemObjectStore


def test_pending_version_becomes_available_and_only_exact_ref_is_readable(
    tmp_path: Path,
) -> None:
    repository = InMemoryObjectMetadataRepository()
    objects = VersionedObjects(FilesystemObjectStore(tmp_path), repository=repository)
    object_id, version_id = uuid4(), uuid4()
    body = b"version one"

    ref = objects.put(
        object_id=object_id,
        version_id=version_id,
        body=BytesIO(body),
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
        content_type="text/plain",
        purpose="runtime_reference",
        correlation_id=uuid4(),
    )

    assert ref.version_id == version_id
    assert repository.get(object_id, version_id).state == "available"
    assert objects.open(ref).read() == body
    with pytest.raises(ObjectNotFound):
        objects.open(ref.__class__(object_id, uuid4(), ref.sha256, ref.size_bytes, ref.content_type))


def test_same_version_retry_is_idempotent_and_conflict_is_explicit(tmp_path: Path) -> None:
    objects = VersionedObjects(FilesystemObjectStore(tmp_path))
    object_id, version_id = uuid4(), uuid4()
    body = b"stable"
    kwargs = {
        "object_id": object_id,
        "version_id": version_id,
        "sha256": hashlib.sha256(body).hexdigest(),
        "size_bytes": len(body),
        "content_type": "application/octet-stream",
    }
    first = objects.put(body=BytesIO(body), **kwargs)
    retry = objects.put(body=BytesIO(body), **kwargs)
    assert retry == first
    with pytest.raises(ObjectVersionConflict):
        objects.put(body=BytesIO(b"different"), **kwargs)


def test_reconcile_completes_matching_pending_write_and_fails_conflict(
    tmp_path: Path,
) -> None:
    repository = InMemoryObjectMetadataRepository()
    store = FilesystemObjectStore(tmp_path)
    objects = VersionedObjects(store, repository=repository)
    object_id, version_id = uuid4(), uuid4()
    body = b"pending bytes"
    digest = hashlib.sha256(body).hexdigest()
    repository.create_pending(
        object_id=object_id,
        version_id=version_id,
        purpose="runtime_reference",
        storage_key=f"objects/{object_id}/{version_id}",
        sha256=digest,
        size_bytes=len(body),
        content_type="application/octet-stream",
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )
    store.put_if_absent(
        storage_key=f"objects/{object_id}/{version_id}",
        body=BytesIO(body),
        sha256=digest,
        size_bytes=len(body),
        content_type="application/octet-stream",
    )

    result = objects.reconcile_pending()

    assert result.completed == 1
    assert repository.get(object_id, version_id).state == "available"


def test_pending_reads_fail_closed(tmp_path: Path) -> None:
    repository = InMemoryObjectMetadataRepository()
    objects = VersionedObjects(FilesystemObjectStore(tmp_path), repository=repository)
    object_id, version_id = uuid4(), uuid4()
    repository.create_pending(
        object_id=object_id,
        version_id=version_id,
        purpose="runtime_reference",
        storage_key=f"objects/{object_id}/{version_id}",
        sha256="0" * 64,
        size_bytes=0,
        content_type="application/octet-stream",
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )
    ref = repository.ref(object_id, version_id)
    with pytest.raises(ObjectNotFound):
        objects.open(ref)
