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

    assert type(dependencies.identity_store) is SqlAlchemyIdentityStore
    assert type(dependencies.job_runtime) is SqlAlchemyJobRuntime
    assert type(dependencies.job_runtime.queue) is RQJobQueue
    assert type(dependencies.object_store) is S3ObjectStore
    assert type(dependencies.identity_access.provider) is SupabaseIdentityAdapter
    assert type(dependencies.identity_access.email) is ResendEmailAdapter


@pytest.mark.parametrize(
    "adapter_kind",
    (
        "memory_store",
        "recording_queue",
        "memory_runtime",
        "filesystem",
        "fake",
        "recording_email",
        "runtime_queue_mismatch",
        "subclass_identity_store",
        "subclass_queue",
        "subclass_runtime",
        "subclass_object_store",
        "subclass_identity_provider",
        "subclass_email",
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
                identity=_unavailable_supabase(), email=_resend_email()
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
    if adapter_kind == "runtime_queue_mismatch":
        return _preview_factories(
            job_runtime=lambda provider, queue, release_id: SqlAlchemyJobRuntime(
                provider.session_factory,
                queue=RecordingJobQueue(),
                release_id=release_id,
            )
        )
    if adapter_kind == "subclass_identity_store":
        return _preview_factories(
            identity_store=lambda settings, provider: _SubclassIdentityStore(
                provider.session_factory,
                fingerprint_key=settings.identity_fingerprint_key.encode(),
                environment=settings.environment,
            )
        )
    if adapter_kind == "subclass_queue":
        return _preview_factories(
            job_queue=lambda connection: _SubclassRQQueue(_Queue())
        )
    if adapter_kind == "subclass_runtime":
        return _preview_factories(
            job_runtime=lambda provider, queue, release_id: _SubclassJobRuntime(
                provider.session_factory, queue=queue, release_id=release_id
            )
        )
    if adapter_kind == "subclass_object_store":
        return _preview_factories(
            object_store=lambda settings: _SubclassS3ObjectStore(
                client=object(), bucket="preview"
            )
        )
    if adapter_kind == "subclass_identity_provider":
        return _preview_factories(
            identity_registry=lambda settings: _registry(
                identity=_SubclassSupabase(), email=_resend_email()
            )
        )
    if adapter_kind == "subclass_email":
        return _preview_factories(
            identity_registry=lambda settings: _registry(
                identity=_supabase_identity(), email=_SubclassResend()
            )
        )
    raise AssertionError(f"unknown adapter kind: {adapter_kind}")


class _SubclassIdentityStore(SqlAlchemyIdentityStore):
    def fingerprint(self, value: str) -> bytes:
        return super().fingerprint(value)


class _SubclassRQQueue(RQJobQueue):
    def publish(self, **kwargs: Any) -> str:
        return super().publish(**kwargs)


class _SubclassJobRuntime(SqlAlchemyJobRuntime):
    def relay_due(self, **kwargs: Any) -> Any:
        return super().relay_due(**kwargs)


class _SubclassS3ObjectStore(S3ObjectStore):
    def stat(self, provider_ref: Any) -> Any:
        return super().stat(provider_ref)


class _SubclassSupabase(SupabaseIdentityAdapter):
    def __init__(self) -> None:
        super().__init__(
            issuer="https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
            capture_origin="https://preview.umbral.invalid",
            client=_Client(),
        )

    def health(self) -> str:
        return "ready"


class _SubclassResend(ResendEmailAdapter):
    def __init__(self) -> None:
        super().__init__(
            sender_email="Umbral <onboarding@resend.dev>",
            webhook_secret="whsec_test",
            sender=lambda params, options: {"id": "test"},
            verifier=lambda options: {},
        )

    def health(self) -> str:
        return "ready"


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


def _unavailable_supabase() -> SupabaseIdentityAdapter:
    identity = _supabase_identity()
    setattr(identity, "health", lambda: "unavailable")
    return identity


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
