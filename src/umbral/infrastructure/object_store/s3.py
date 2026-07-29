"""S3-compatible private object adapter (R2 and MinIO)."""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from typing import Any, BinaryIO
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


class S3ObjectStore:
    """S3 adapter using immutable keys and conditional creation."""

    def __init__(
        self,
        client: Any,
        bucket: str,
        endpoint_url: str | None = None,
    ) -> None:
        del endpoint_url  # The configured boto client owns endpoint details.
        if not bucket:
            raise ValueError("bucket must not be empty")
        self.client = client
        self.bucket = bucket
        self._keys_by_token: dict[str, str] = {}
        self._tokens_by_key: dict[str, str] = {}

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
        bytes_body = body.read()
        if not isinstance(bytes_body, bytes):
            raise ObjectIntegrityError("object body did not return bytes")
        if (
            len(bytes_body) != size_bytes
            or hashlib.sha256(bytes_body).hexdigest() != digest
        ):
            raise ObjectIntegrityError("declared object integrity does not match bytes")

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=BytesIO(bytes_body),
                ContentType=media_type,
                Metadata={"sha256": digest, "size_bytes": str(size_bytes)},
                IfNoneMatch="*",
            )
        except Exception as error:
            if not _is_precondition_failure(error):
                if _is_missing(error):
                    raise ObjectNotFound("object provider is unavailable") from error
                # Providers without If-None-Match support are still safe here:
                # head/stat arbitrates an existing immutable key before retry.
                if not _is_conditional_unsupported(error):
                    raise ObjectIntegrityError(
                        "object provider write failed"
                    ) from error
                if _remote_exists(self.client, self.bucket, key):
                    info = self._stat_key(key)
                    _ensure_match(info, digest, size_bytes, media_type)
                    return self._ref_for_key(key)
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=BytesIO(bytes_body),
                    ContentType=media_type,
                    Metadata={"sha256": digest, "size_bytes": str(size_bytes)},
                )
            else:
                info = self._stat_key(key)
                _ensure_match(info, digest, size_bytes, media_type)
                return self._ref_for_key(key)

        info = self._stat_key(key)
        _ensure_match(info, digest, size_bytes, media_type)
        return self._ref_for_key(key)

    def open(self, provider_ref: ProviderObjectRef) -> BinaryIO:
        key = self._key_for_ref(provider_ref)
        info = self._stat_key(key)
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            body = result["Body"].read()
        except Exception as error:
            raise ObjectIntegrityError("provider bytes could not be read") from error
        if not isinstance(body, bytes):
            raise ObjectIntegrityError("provider body did not return bytes")
        _ensure_body(body, info.sha256, info.size_bytes)
        return BytesIO(body)

    def stat(self, provider_ref: ProviderObjectRef) -> ObjectInfo:
        return self._stat_key(self._key_for_ref(provider_ref))

    def ref_for_key(self, storage_key: str) -> ProviderObjectRef:
        return self._ref_for_key(_validate_key(storage_key))

    def _stat_key(self, key: str) -> ObjectInfo:
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if _is_missing(error):
                raise ObjectNotFound("provider object is unavailable") from error
            raise ObjectIntegrityError("provider metadata could not be read") from error
        metadata = head.get("Metadata") or {}
        digest = metadata.get("sha256")
        size = head.get("ContentLength")
        content_type = head.get("ContentType", "application/octet-stream")
        try:
            normalized_digest = _validate_digest(str(digest))
            normalized_size = int(size)
            normalized_type = _normalize_content_type(str(content_type))
        except (TypeError, ValueError) as error:
            raise ObjectIntegrityError("provider metadata is invalid") from error
        try:
            result = self.client.get_object(Bucket=self.bucket, Key=key)
            body = result["Body"].read()
        except Exception as error:
            raise ObjectIntegrityError(
                "provider bytes could not be verified"
            ) from error
        if not isinstance(body, bytes):
            raise ObjectIntegrityError("provider body did not return bytes")
        _ensure_body(body, normalized_digest, normalized_size)
        provider_ref = self._ref_for_key(key)
        return ObjectInfo(
            provider_ref=provider_ref,
            sha256=normalized_digest,
            size_bytes=normalized_size,
            content_type=normalized_type,
            # Persist the adapter's opaque ref, not a bucket/key or provider
            # version that another process could mistake for an application ref.
            provider_version=provider_ref.value,
        )

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


def _ensure_match(
    info: ObjectInfo, digest: str, size: int, content_type: str
) -> None:
    if (
        info.sha256 != digest
        or info.size_bytes != size
        or info.content_type != content_type
    ):
        raise ObjectVersionConflict("immutable provider key has different content")


def _ensure_body(body: bytes, digest: str, size: int) -> None:
    if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
        raise ObjectIntegrityError("provider bytes failed integrity verification")


def _remote_exists(client: Any, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except Exception as error:
        if _is_missing(error):
            return False
        raise ObjectIntegrityError("provider metadata could not be read") from error
    return True


def _error_code(error: Exception) -> str:
    response = getattr(error, "response", {})
    error_info = response.get("Error", {}) if isinstance(response, dict) else {}
    return str(error_info.get("Code", ""))


def _is_missing(error: Exception) -> bool:
    return _error_code(error) in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}


def _is_precondition_failure(error: Exception) -> bool:
    return _error_code(error) in {
        "412",
        "PreconditionFailed",
        "ConditionalRequestConflict",
    }


def _is_conditional_unsupported(error: Exception) -> bool:
    return isinstance(error, TypeError) or _error_code(error) in {
        "InvalidRequest",
        "NotImplemented",
        "InvalidArgument",
    }


def _validate_key(storage_key: str) -> str:
    if (
        not storage_key
        or "\\" in storage_key
        or storage_key.startswith("/")
        or ".." in storage_key.split("/")
    ):
        raise ValueError("storage key must be an opaque relative path")
    if not storage_key.startswith("objects/") or len(storage_key.split("/")) < 3:
        raise ValueError("storage key must be an opaque objects/<id>/<version> path")
    return storage_key


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
