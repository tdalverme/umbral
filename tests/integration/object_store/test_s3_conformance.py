"""S3/MinIO conformance seam tests (T058).

The live MinIO matrix is intentionally opt-in in local runs. The fake client
exercises the same conditional-put/stat/open outcome without requiring Docker.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

from umbral.infrastructure.object_store.s3 import S3ObjectStore


class _FakeBody:
    def __init__(self, body: bytes) -> None:
        self._body = BytesIO(body)

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def close(self) -> None:
        self._body.close()


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        key = (kwargs["Bucket"], kwargs["Key"])
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            error = RuntimeError("PreconditionFailed")
            setattr(error, "response", {"Error": {"Code": "PreconditionFailed"}})
            raise error
        body = kwargs["Body"].read()
        self.objects[key] = {
            "Body": body,
            "ContentLength": len(body),
            "ContentType": kwargs.get("ContentType", "application/octet-stream"),
            "Metadata": kwargs.get("Metadata", {}),
            "VersionId": "v1",
        }
        return {"VersionId": "v1"}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            return dict(self.objects[(Bucket, Key)])
        except KeyError as error:
            missing = RuntimeError("NoSuchKey")
            setattr(missing, "response", {"Error": {"Code": "NoSuchKey"}})
            raise missing from error

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        result = self.head_object(Bucket=Bucket, Key=Key)
        result["Body"] = _FakeBody(result["Body"])
        return result


def test_s3_provider_refs_are_opaque_and_conform_to_filesystem_outcomes() -> None:
    client = _FakeS3()
    store = S3ObjectStore(client=client, bucket="private")
    body = b"remote bytes"
    digest = hashlib.sha256(body).hexdigest()
    ref = store.put_if_absent(
        storage_key="objects/one/v1",
        body=BytesIO(body),
        sha256=digest,
        size_bytes=len(body),
        content_type="application/octet-stream",
    )

    assert "private" not in ref.value
    assert "objects/one/v1" not in ref.value
    assert store.stat(ref).sha256 == digest
    assert store.open(ref).read() == body
