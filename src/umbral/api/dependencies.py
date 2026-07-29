"""Composition-time dependencies for the API runtime surface."""
# ruff: noqa: E501

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.authorization import AccessControl
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.objects.ports import ObjectStore
from umbral.application.runtime.readiness import (
    ReadinessCheck,
    ReadinessModule,
    ReadinessProbe,
)
from umbral.application.runtime.version import (
    ReleaseArtifact,
    ReleaseManifest,
    load_release_manifest,
)
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.identity.registry import build_identity_registry
from umbral.infrastructure.object_store.factory import build_object_store
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue

_LOCAL_RELEASE_MANIFEST = "<local>"


@dataclass(frozen=True, slots=True)
class RuntimeDependencies:
    """Immutable values shared by the runtime routes."""

    settings: Settings
    release: ReleaseManifest
    readiness: ReadinessModule
    object_store: ObjectStore
    identity_store: InMemoryIdentityStore
    identity_access: IdentityAccess
    access_control: AccessControl
    administration: AccessAdministration
    job_runtime: InMemoryJobRuntime | None = None


def build_runtime_dependencies(
    environment: Mapping[str, str] | None = None,
) -> RuntimeDependencies:
    """Build local-safe defaults or validate an explicitly configured runtime."""

    values = os.environ if environment is None else environment
    settings = _load_settings(values)
    release = _load_release(settings)
    object_store = build_object_store(settings)
    identity_store = InMemoryIdentityStore(fingerprint_key=settings.identity_fingerprint_key.encode())
    identity_registry = build_identity_registry(settings)
    identity_access = IdentityAccess(identity_store, identity_registry.identity, identity_registry.email, environment=settings.environment, capture_origin=settings.identity_capture_origin)
    job_queue = RecordingJobQueue()
    job_runtime = InMemoryJobRuntime(queue=job_queue)
    identity_access.job_runtime = job_runtime
    readiness = ReadinessModule(
        surface="api",
        release_id=release.release_id,
        probes=(
            ReadinessProbe(
                name="runtime_config",
                critical=True,
                check=lambda: ReadinessCheck(
                    name="runtime_config", state="ready", critical=True
                ),
            ),
        ),
    )
    return RuntimeDependencies(
        settings=settings,
        release=release,
        readiness=readiness,
        object_store=object_store,
        identity_store=identity_store,
        identity_access=identity_access,
        access_control=AccessControl(identity_store),
        administration=AccessAdministration(identity_store),
        job_runtime=job_runtime,
    )


def _load_settings(environment: Mapping[str, str]) -> Settings:
    values = {
        key: value
        for key, value in environment.items()
        if key.startswith(
            ("UMBRAL_", "DATABASE_", "REDIS_", "OBJECT_STORE_", "OTEL_", "SENTRY_", "IDENTITY_", "EMAIL_", "RESEND_", "SESSION_")
        )
    }
    if not values:
        return Settings.from_environment(_local_settings())
    return Settings.from_environment(values)


def _local_settings() -> dict[str, str]:
    return {
        "UMBRAL_ENV": "local",
        "UMBRAL_RELEASE_ID": "foundation-local",
        "UMBRAL_RELEASE_MANIFEST": _LOCAL_RELEASE_MANIFEST,
        "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "OBJECT_STORE_BACKEND": "filesystem",
        "OBJECT_STORE_ROOT": ".umbral-local",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
        "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
        "IDENTITY_PROVIDER": "fake",
        "IDENTITY_ISSUER": "fake://local",
        "IDENTITY_CAPTURE_ORIGIN": "http://localhost:3000",
        "EMAIL_PROVIDER": "recording",
        "UMBRAL_BFF_TOKEN": "local-bff-token",
        "IDENTITY_FINGERPRINT_KEY": "local-identity-fingerprint-key",
        "SESSION_COOKIE_NAME": "umbral_local_session",
        "SESSION_SECURE": "false",
    }


def _load_release(settings: Settings) -> ReleaseManifest:
    if settings.release_manifest != _LOCAL_RELEASE_MANIFEST:
        return load_release_manifest(Path(settings.release_manifest))
    return ReleaseManifest(
        release_id=settings.release_id,
        git_sha="0" * 40,
        built_at="2026-01-01T00:00:00Z",
        contract_major=1,
        database_revision="local",
        config_schema_version=1,
        artifacts={
            "web": ReleaseArtifact(
                image="umbral/web",
                digest="sha256:" + "0" * 64,
                platform="linux/amd64",
            ),
            "runtime": ReleaseArtifact(
                image="umbral/runtime",
                digest="sha256:" + "0" * 64,
                platform="linux/amd64",
            ),
        },
        manifest_sha256="0" * 64,
    )
