"""Private filesystem object adapter with exclusive immutable writes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import IO, BinaryIO
from uuid import uuid4

from umbral.application.objects.contracts import (
    ObjectInfo,
    ObjectIntegrityError,
    ObjectNotFound,
    ObjectVersionConflict,
    ProviderObjectRef,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_TYPE = re.compile(r"^[a-z0-9!#$&^_.+\-]+/[a-z0-9!#$&^_.+\-]+$")
_CHUNK_SIZE = 1024 * 1024


class FilesystemObjectStore:
    """Store immutable bytes below a private root directory.

    Provider refs are random opaque tokens held by this adapter. The storage
    key remains an implementation detail and never appears in returned reprs.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._keys_by_token: dict[str, str] = {}
        self._tokens_by_key: dict[str, str] = {}
        self._publish_lock = Lock()

    def put_if_absent(
        self,
        *,
        storage_key: str,
        body: BinaryIO,
        sha256: str,
        size_bytes: int,
        content_type: str,
    ) -> ProviderObjectRef:
        key = _validate_key(storage_key)
        digest = _validate_digest(sha256)
        media_type = _normalize_content_type(content_type)
        if size_bytes < 0:
            raise ObjectIntegrityError("declared object size is invalid")
        target = self.root / PurePosixPath(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w+b", prefix=".pending-", dir=target.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            actual_digest, actual_size = _copy_and_hash(body, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())

        if actual_digest != digest or actual_size != size_bytes:
            temporary_path.unlink(missing_ok=True)
            raise ObjectIntegrityError("declared object integrity does not match bytes")

        try:
            with self._publish_lock:
                published = _publish_exclusive(temporary_path, target)
                metadata_path = _metadata_path(target)
                if published:
                    self._publish_metadata(
                        metadata_path,
                        {
                            "sha256": digest,
                            "size_bytes": size_bytes,
                            "content_type": media_type,
                        },
                    )
                else:
                    existing = self._stat_path(target, metadata_path)
                    if (
                        existing.sha256 != digest
                        or existing.size_bytes != size_bytes
                        or existing.content_type != media_type
                    ):
                        raise ObjectVersionConflict(
                            "immutable provider key has different content"
                        )
        finally:
            temporary_path.unlink(missing_ok=True)

        return self._ref_for_key(key)

    def open(self, provider_ref: ProviderObjectRef) -> BinaryIO:
        key = self._key_for_ref(provider_ref)
        target = self.root / PurePosixPath(key)
        metadata_path = _metadata_path(target)
        info = self._stat_path(target, metadata_path)
        try:
            body = target.read_bytes()
        except OSError as error:
            raise ObjectIntegrityError("provider bytes could not be read") from error
        actual_digest = hashlib.sha256(body).hexdigest()
        if len(body) != info.size_bytes or actual_digest != info.sha256:
            raise ObjectIntegrityError("provider bytes failed integrity verification")
        return BytesIO(body)

    def stat(self, provider_ref: ProviderObjectRef) -> ObjectInfo:
        key = self._key_for_ref(provider_ref)
        target = self.root / PurePosixPath(key)
        return self._stat_path(target, _metadata_path(target))

    def ref_for_key(self, storage_key: str) -> ProviderObjectRef:
        """Return an opaque ref for reconciliation of a known immutable key."""

        return self._ref_for_key(_validate_key(storage_key))

    def _ref_for_key(self, key: str) -> ProviderObjectRef:
        token = self._tokens_by_key.get(key)
        if token is None:
            token = uuid4().hex
            self._tokens_by_key[key] = token
            self._keys_by_token[token] = key
        return ProviderObjectRef(token)

    def _key_for_ref(self, provider_ref: ProviderObjectRef) -> str:
        try:
            return self._keys_by_token[provider_ref.value]
        except KeyError as error:
            raise ObjectNotFound("provider object reference is unavailable") from error

    def _stat_path(self, target: Path, metadata_path: Path) -> ObjectInfo:
        if not target.is_file():
            raise ObjectNotFound("provider object is unavailable")
        if not metadata_path.is_file():
            raise ObjectIntegrityError("provider metadata is unavailable")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected_digest = _validate_digest(str(metadata["sha256"]))
            expected_size = int(metadata["size_bytes"])
            content_type = _normalize_content_type(str(metadata["content_type"]))
            body = target.read_bytes()
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise ObjectIntegrityError("provider metadata is invalid") from error
        actual_digest = hashlib.sha256(body).hexdigest()
        if len(body) != expected_size or actual_digest != expected_digest:
            raise ObjectIntegrityError("provider bytes failed integrity verification")
        return ObjectInfo(
            provider_ref=self._ref_for_key(_key_from_target(self.root, target)),
            sha256=actual_digest,
            size_bytes=len(body),
            content_type=content_type,
        )

    def _publish_metadata(self, path: Path, metadata: dict[str, object]) -> None:
        serialized = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".metadata-",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            if not _publish_exclusive(temporary_path, path):
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != metadata:
                    raise ObjectVersionConflict("immutable provider metadata conflicts")
        finally:
            temporary_path.unlink(missing_ok=True)


def _copy_and_hash(body: BinaryIO, target: IO[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := body.read(_CHUNK_SIZE):
        if not isinstance(chunk, bytes):
            raise ObjectIntegrityError("object body did not return bytes")
        target.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _publish_exclusive(source: Path, target: Path) -> bool:
    try:
        os.link(source, target)
        return True
    except FileExistsError:
        return False
    except OSError:
        # Some Windows volumes do not permit hard links. The fallback remains
        # exclusive within this process and never replaces an existing target.
        if target.exists():
            return False
        try:
            with target.open("xb") as destination, source.open("rb") as source_file:
                while chunk := source_file.read(_CHUNK_SIZE):
                    destination.write(chunk)
        except FileExistsError:
            return False
        source.unlink(missing_ok=True)
        return True


def _metadata_path(target: Path) -> Path:
    return target.with_name(target.name + ".meta.json")


def _key_from_target(root: Path, target: Path) -> str:
    try:
        return target.relative_to(root).as_posix()
    except ValueError as error:
        raise ObjectIntegrityError("provider path escaped private root") from error


def _validate_key(storage_key: str) -> str:
    path = PurePosixPath(storage_key)
    if (
        not storage_key
        or "\\" in storage_key
        or path.is_absolute()
        or ".." in path.parts
        or path.parts[0:1] != ("objects",)
        or len(path.parts) < 3
    ):
        raise ValueError("storage key must be an opaque objects/<id>/<version> path")
    return path.as_posix()


def _validate_digest(value: str) -> str:
    digest = value.lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError("sha256 must be lowercase hexadecimal")
    return digest


def _normalize_content_type(value: str) -> str:
    media_type = value.strip().lower()
    if not _CONTENT_TYPE.fullmatch(media_type):
        raise ValueError("content_type must be a normalized media type")
    return media_type
