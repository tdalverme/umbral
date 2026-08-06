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
from umbral.application.identity.ports import IdentityStore
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.ports import JobRuntime
from umbral.application.objects.ports import ObjectStore
from umbral.application.radar.service import RadarService
from umbral.application.runtime.readiness import ReadinessModule
from umbral.application.runtime.version import (
    ReleaseArtifact,
    ReleaseManifest,
    load_release_manifest,
    parse_release_manifest,
)
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.runtime.composition import (
    RuntimeCompositionFactories,
    compose_runtime,
)
from umbral.infrastructure.runtime.heartbeat import RuntimeHeartbeatWriter

_LOCAL_RELEASE_MANIFEST = "<local>"


@dataclass(frozen=True, slots=True)
class RuntimeDependencies:
    """Immutable values shared by the runtime routes."""

    settings: Settings
    release: ReleaseManifest
    readiness: ReadinessModule
    object_store: ObjectStore
    identity_store: IdentityStore
    identity_access: IdentityAccess
    access_control: AccessControl
    administration: AccessAdministration
    ingestion: ImportRunService
    radar: RadarService | None = None
    heartbeat_writer: RuntimeHeartbeatWriter | None = None
    job_runtime: JobRuntime | None = None


def build_runtime_dependencies(
    environment: Mapping[str, str] | None = None,
    *,
    factories: RuntimeCompositionFactories | None = None,
) -> RuntimeDependencies:
    """Build local-safe defaults or validate an explicitly configured runtime."""

    values = os.environ if environment is None else environment
    settings = _load_settings(values)
    release = _load_release(settings)
    composition = compose_runtime(
        settings=settings, release=release, factories=factories
    )
    heartbeat_writer = None
    if settings.environment != "local":
        heartbeat_writer = RuntimeHeartbeatWriter(
            SessionProvider(settings.database_url).session_factory,
            environment=settings.environment,
            release=release,
        )
    return RuntimeDependencies(
        settings=settings,
        release=release,
        readiness=composition.readiness,
        object_store=composition.object_store,
        identity_store=composition.identity_store,
        identity_access=composition.identity_access,
        access_control=composition.access_control,
        administration=composition.administration,
        ingestion=composition.ingestion,
        radar=composition.radar,
        heartbeat_writer=heartbeat_writer,
        job_runtime=composition.job_runtime,
    )


def _load_settings(environment: Mapping[str, str]) -> Settings:
    values = {
        key: value
        for key, value in environment.items()
        if key.startswith(
            (
                "UMBRAL_",
                "DATABASE_",
                "REDIS_",
                "OBJECT_STORE_",
                "OTEL_",
                "SENTRY_",
                "IDENTITY_",
                "SUPABASE_",
                "EMAIL_",
                "RESEND_",
                "SESSION_",
            )
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
    value = settings.release_manifest
    if value == _LOCAL_RELEASE_MANIFEST:
        return _synthetic_release(settings)
    if value.lstrip().startswith("{"):
        return parse_release_manifest(value)
    return load_release_manifest(Path(value))


def _synthetic_release(settings: Settings) -> ReleaseManifest:
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
