"""Composition-time dependencies for the API runtime surface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from umbral.application.runtime.readiness import (
    ReadinessCheck,
    ReadinessModule,
)
from umbral.application.runtime.version import (
    ReleaseArtifact,
    ReleaseManifest,
    load_release_manifest,
)
from umbral.infrastructure.config.settings import Settings

_LOCAL_RELEASE_MANIFEST = "<local>"


@dataclass(frozen=True, slots=True)
class RuntimeDependencies:
    """Immutable values shared by the runtime routes."""

    settings: Settings
    release: ReleaseManifest
    readiness: ReadinessModule


def build_runtime_dependencies(
    environment: Mapping[str, str] | None = None,
) -> RuntimeDependencies:
    """Build local-safe defaults or validate an explicitly configured runtime."""

    values = os.environ if environment is None else environment
    settings = _load_settings(values)
    release = _load_release(settings)
    readiness = ReadinessModule(
        surface="api",
        release_id=release.release_id,
        probes=(
            lambda: ReadinessCheck(
                name="runtime_config", state="ready", critical=True
            ),
        ),
    )
    return RuntimeDependencies(settings=settings, release=release, readiness=readiness)


def _load_settings(environment: Mapping[str, str]) -> Settings:
    values = {
        key: value
        for key, value in environment.items()
        if key.startswith(
            ("UMBRAL_", "DATABASE_", "REDIS_", "OBJECT_STORE_", "OTEL_", "SENTRY_")
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
