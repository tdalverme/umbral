"""Application-level object-store conformance tests (T057)."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from umbral.application.objects.contracts import (
    ObjectIntegrityError,
    ObjectVersionConflict,
)
from umbral.infrastructure.object_store.filesystem import FilesystemObjectStore


def _declared(body: bytes) -> tuple[str, int]:
    return hashlib.sha256(body).hexdigest(), len(body)


def test_filesystem_round_trip_and_two_immutable_versions(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    first = b"first version"
    second = b"second version"
    first_hash, first_size = _declared(first)
    second_hash, second_size = _declared(second)

    first_ref = store.put_if_absent(
        storage_key="objects/one/v1",
        body=BytesIO(first),
        sha256=first_hash,
        size_bytes=first_size,
        content_type="text/plain",
    )
    second_ref = store.put_if_absent(
        storage_key="objects/one/v2",
        body=BytesIO(second),
        sha256=second_hash,
        size_bytes=second_size,
        content_type="text/plain",
    )

    assert first_ref != second_ref
    assert store.open(first_ref).read() == first
    assert store.open(second_ref).read() == second
    assert store.stat(first_ref).content_type == "text/plain"
    assert store.stat(first_ref).sha256 == first_hash


def test_same_key_same_content_is_idempotent_but_different_content_conflicts(
    tmp_path: Path,
) -> None:
    store = FilesystemObjectStore(tmp_path)
    body = b"immutable"
    digest, size = _declared(body)
    first = store.put_if_absent(
        storage_key="objects/one/v1",
        body=BytesIO(body),
        sha256=digest,
        size_bytes=size,
        content_type="application/octet-stream",
    )
    retry = store.put_if_absent(
        storage_key="objects/one/v1",
        body=BytesIO(body),
        sha256=digest,
        size_bytes=size,
        content_type="application/octet-stream",
    )
    assert retry == first

    changed = b"changed"
    changed_hash, changed_size = _declared(changed)
    with pytest.raises(ObjectVersionConflict):
        store.put_if_absent(
            storage_key="objects/one/v1",
            body=BytesIO(changed),
            sha256=changed_hash,
            size_bytes=changed_size,
            content_type="application/octet-stream",
        )


@pytest.mark.parametrize(
    ("declared_hash", "declared_size"),
    [("0" * 64, 4), (hashlib.sha256(b"bytes").hexdigest(), 4)],
)
def test_declaration_mismatch_fails_closed(
    tmp_path: Path, declared_hash: str, declared_size: int
) -> None:
    store = FilesystemObjectStore(tmp_path)
    with pytest.raises(ObjectIntegrityError):
        store.put_if_absent(
            storage_key=f"objects/{uuid4()}/v1",
            body=BytesIO(b"bytes"),
            sha256=declared_hash,
            size_bytes=declared_size,
            content_type="application/octet-stream",
        )


def test_corrupted_provider_bytes_are_never_returned_as_valid(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    body = b"integrity"
    digest, size = _declared(body)
    provider_ref = store.put_if_absent(
        storage_key="objects/one/v1",
        body=BytesIO(body),
        sha256=digest,
        size_bytes=size,
        content_type="text/plain",
    )
    (tmp_path / "objects" / "one" / "v1").write_bytes(b"tampered")

    with pytest.raises(ObjectIntegrityError):
        store.stat(provider_ref)
    with pytest.raises(ObjectIntegrityError):
        store.open(provider_ref)
