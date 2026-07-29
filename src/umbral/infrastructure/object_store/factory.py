"""Environment composition for local filesystem and remote S3 adapters."""

from __future__ import annotations

from typing import Any

from umbral.application.objects.ports import ObjectStore
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.object_store.filesystem import FilesystemObjectStore
from umbral.infrastructure.object_store.s3 import S3ObjectStore


def build_object_store(
    settings: Settings,
    *,
    client: Any | None = None,
) -> ObjectStore:
    """Build the configured adapter; credentials remain in infrastructure."""

    if settings.object_store_backend == "filesystem":
        return FilesystemObjectStore(settings.object_store_root or ".umbral-local")
    bucket = settings.object_store_bucket
    if not bucket:
        raise ValueError("OBJECT_STORE_BUCKET is required for the s3 backend")
    if client is None:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.object_store_endpoint_url,
            aws_access_key_id=settings.object_store_access_key,
            aws_secret_access_key=settings.object_store_secret_key,
        )
    return S3ObjectStore(
        client=client,
        bucket=bucket,
        endpoint_url=settings.object_store_endpoint_url,
    )
