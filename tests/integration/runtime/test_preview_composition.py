"""Preview composition uses only durable adapters and isolates provider outages."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from umbral.api.dependencies import build_runtime_dependencies
from umbral.application.jobs.ports import JobRuntime
from umbral.application.runtime.readiness import ReadinessCheck
from umbral.infrastructure.db.repositories.identity import (
    InMemoryIdentityStore,
    SqlAlchemyIdentityStore,
)
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.email.resend import ResendEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.identity.registry import (
    EnvironmentIdentityPolicy,
    IdentityProviderRegistry,
)
from umbral.infrastructure.identity.supabase import SupabaseIdentityAdapter
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.object_store.filesystem import FilesystemObjectStore
from umbral.infrastructure.object_store.s3 import S3ObjectStore
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.queue.rq_queue import RQJobQueue
from umbral.infrastructure.runtime.composition import RuntimeCompositionFactories


class _Client:
    auth = object()


class _Queue:
    serializer: object | None = None


class _Redis:
    def ping(self) -> bool:
        return True


def test_preview_runtime_composes_only_durable_concrete_adapters() -> None:
    dependencies = build_runtime_dependencies(
        _preview_environment(), factories=_preview_factories()
    )

    assert isinstance(dependencies.identity_store, SqlAlchemyIdentityStore)
    assert isinstance(dependencies.job_runtime, SqlAlchemyJobRuntime)
    assert isinstance(dependencies.job_runtime.queue, RQJobQueue)
    assert isinstance(dependencies.object_store, S3ObjectStore)
    assert isinstance(dependencies.identity_access.provider, SupabaseIdentityAdapter)
    assert isinstance(dependencies.identity_access.email, ResendEmailAdapter)


@pytest.mark.parametrize(
    "adapter_kind",
    (
        "memory_store",
        "recording_queue",
        "memory_runtime",
        "filesystem",
        "fake",
        "recording_email",
    ),
)
def test_preview_runtime_rejects_every_local_or_recording_adapter(
    adapter_kind: str,
) -> None:
    factories = _preview_factories_for(adapter_kind)

    with pytest.raises(ValueError, match="preview runtime requires durable adapters"):
        build_runtime_dependencies(_preview_environment(), factories=factories)


def test_preview_critical_probe_failure_is_not_ready() -> None:
    dependencies = build_runtime_dependencies(
        _preview_environment(),
        factories=_preview_factories(
            readiness_check=lambda name, critical: ReadinessCheck(
                name=name,
                state="unavailable" if name == "postgis" else "ready",
                critical=critical,
                code="postgis.unavailable" if name == "postgis" else None,
            )
        ),
    )

    assert dependencies.readiness.evaluate().state == "not_ready"


def test_preview_defers_persistence_probe_until_readiness() -> None:
    dependencies = build_runtime_dependencies(
        _preview_environment(),
        factories=_preview_factories(
            real_readiness=True,
            persistence_probe=lambda provider, revision: _raise_probe_failure(),
        ),
    )

    assert dependencies.readiness.evaluate().state == "not_ready"


def test_preview_provider_outage_only_degrades_new_login_capability() -> None:
    dependencies = build_runtime_dependencies(
        _preview_environment(),
        factories=_preview_factories(
            identity_registry=lambda settings: _registry(
                identity=_UnavailableSupabase(), email=_resend_email()
            )
        ),
    )

    report = dependencies.readiness.evaluate()

    assert report.state == "degraded"
    identity_check = next(
        check for check in report.checks if check.name == "identity_provider"
    )
    assert identity_check.critical is False
    assert identity_check.state == "unavailable"


class _UnavailableSupabase(SupabaseIdentityAdapter):
    def __init__(self) -> None:
        super().__init__(
            issuer="https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
            capture_origin="https://preview.umbral.invalid",
            client=_Client(),
        )

    def health(self) -> str:
        return "unavailable"


def _preview_factories(
    *,
    identity_store: Any | None = None,
    identity_registry: Any | None = None,
    job_queue: Any | None = None,
    job_runtime: Any | None = None,
    object_store: Any | None = None,
    readiness_check: Any | None = None,
    persistence_probe: Any | None = None,
    real_readiness: bool = False,
) -> RuntimeCompositionFactories:
    defaults = RuntimeCompositionFactories(
        session_provider=lambda database_url: SessionProvider("sqlite+pysqlite://"),
        identity_registry=lambda settings: _registry(
            identity=_supabase_identity(), email=_resend_email()
        ),
        redis_connection=lambda url: _Redis(),
        job_queue=lambda connection: RQJobQueue(_Queue()),
        object_store=lambda settings: S3ObjectStore(client=object(), bucket="preview"),
        persistence_probe=lambda provider, revision: _ready_persistence_probe(),
        readiness_check=lambda name, critical: ReadinessCheck(
            name=name, state="ready", critical=critical
        ),
    )
    return replace(
        defaults,
        identity_store=identity_store or defaults.identity_store,
        identity_registry=identity_registry or defaults.identity_registry,
        job_queue=job_queue or defaults.job_queue,
        job_runtime=job_runtime or defaults.job_runtime,
        object_store=object_store or defaults.object_store,
        persistence_probe=persistence_probe or defaults.persistence_probe,
        readiness_check=(
            None
            if real_readiness
            else readiness_check or defaults.readiness_check
        ),
    )


def _preview_factories_for(adapter_kind: str) -> RuntimeCompositionFactories:
    if adapter_kind == "memory_store":
        return _preview_factories(
            identity_store=lambda settings, provider: InMemoryIdentityStore()
        )
    if adapter_kind == "recording_queue":
        return _preview_factories(job_queue=lambda connection: RecordingJobQueue())
    if adapter_kind == "memory_runtime":
        return _preview_factories(
            job_runtime=lambda provider, queue, release_id: cast(
                JobRuntime, RecordingJobQueue()
            )
        )
    if adapter_kind == "filesystem":
        return _preview_factories(
            object_store=lambda settings: FilesystemObjectStore(".tmp")
        )
    if adapter_kind == "fake":
        return _preview_factories(
            identity_registry=lambda settings: _registry(
                identity=FakeIdentityProvider(), email=_resend_email()
            )
        )
    if adapter_kind == "recording_email":
        return _preview_factories(
            identity_registry=lambda settings: _registry(
                identity=_supabase_identity(), email=RecordingEmailAdapter()
            )
        )
    raise AssertionError(f"unknown adapter kind: {adapter_kind}")


def _registry(
    *,
    identity: SupabaseIdentityAdapter | FakeIdentityProvider,
    email: ResendEmailAdapter | RecordingEmailAdapter,
) -> IdentityProviderRegistry:
    return IdentityProviderRegistry(
        identity=identity,
        email=email,
        enabled=True,
        policy=EnvironmentIdentityPolicy(
            environment="preview",
            issuer="https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
            capture_origin="https://preview.umbral.invalid",
            email_provider=email.provider,
        ),
    )


def _supabase_identity() -> SupabaseIdentityAdapter:
    return SupabaseIdentityAdapter(
        issuer="https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
        capture_origin="https://preview.umbral.invalid",
        client=_Client(),
    )


def _resend_email() -> ResendEmailAdapter:
    return ResendEmailAdapter(
        sender_email="Umbral <onboarding@resend.dev>",
        webhook_secret="whsec_test",
        sender=lambda params, options: {"id": "test"},
        verifier=lambda options: {},
    )


def _ready_persistence_probe() -> Any:
    from umbral.infrastructure.db.readiness import DatabaseReadiness, PersistenceProbe

    return PersistenceProbe(
        database=DatabaseReadiness(
            state="ready",
            code=None,
            details={"extension_postgis": "ready", "extension_vector": "ready"},
        ),
        alembic_head="foundation_0001",
    )


def _raise_probe_failure() -> Any:
    raise RuntimeError("database unavailable")


def _preview_environment() -> dict[str, str]:
    return {
        "UMBRAL_ENV": "preview",
        "UMBRAL_RELEASE_ID": "preview-test",
        "UMBRAL_RELEASE_MANIFEST": "tests/fixtures/release-manifests/valid.json",
        "UMBRAL_RELEASE_DIGEST": "sha256:" + "a" * 64,
        "DATABASE_URL": "postgresql://user:pass@db.preview.invalid/app",
        "REDIS_URL": "redis://redis.railway.internal/0",
        "OBJECT_STORE_BACKEND": "s3",
        "OBJECT_STORE_BUCKET": "umbral-preview-primary",
        "OBJECT_STORE_ENDPOINT_URL": "https://r2.preview.invalid",
        "OBJECT_STORE_ACCESS_KEY": "test-key",
        "OBJECT_STORE_SECRET_KEY": "test-secret",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.preview.invalid",
        "SENTRY_DSN": "https://sentry.invalid/1",
        "UMBRAL_API_BASE_URL": "http://api.railway.internal:8000",
        "UMBRAL_ACCESS_MODE": "product_session",
        "IDENTITY_PROVIDER": "supabase",
        "SUPABASE_URL": "https://bpwgyvetbneghrtxcadm.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test_value",
        "IDENTITY_ISSUER": "https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
        "IDENTITY_CAPTURE_ORIGIN": "https://preview.umbral.invalid",
        "EMAIL_PROVIDER": "resend",
        "RESEND_API_KEY": "re_test_value",
        "RESEND_FROM_EMAIL": "Umbral <onboarding@resend.dev>",
        "EMAIL_WEBHOOK_SECRET": "whsec_test_value",
    }
