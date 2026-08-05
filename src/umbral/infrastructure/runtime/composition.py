"""Select environment-safe API adapters without exposing concrete types upstream."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal, cast

from redis import Redis

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.ports import IdentityStore
from umbral.application.jobs.ports import JobQueue, JobRuntime
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.objects.ports import ObjectStore
from umbral.application.runtime.readiness import (
    DependencyCheckName,
    ReadinessCheck,
    ReadinessModule,
    ReadinessProbe,
    login_dependency_probes,
)
from umbral.application.runtime.version import ReleaseManifest
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.readiness import PersistenceProbe
from umbral.infrastructure.db.repositories.identity import (
    InMemoryIdentityStore,
    SqlAlchemyIdentityStore,
)
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.email.resend import ResendEmailAdapter
from umbral.infrastructure.identity.registry import (
    IdentityProviderRegistry,
    build_identity_registry,
)
from umbral.infrastructure.identity.supabase import SupabaseIdentityAdapter
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.object_store.factory import build_object_store
from umbral.infrastructure.object_store.s3 import S3ObjectStore
from umbral.infrastructure.observability.otel import record_dependency_metric
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.queue.rq_queue import RQJobQueue

_MARKER_BODY = b"umbral-preview-readiness-v1"
_MARKER_DIGEST = hashlib.sha256(_MARKER_BODY).hexdigest()
_MARKER_KEY = "objects/runtime-readiness/preview-v1"


def _build_session_provider(database_url: str) -> SessionProvider:
    """Select psycopg explicitly; settings retain their provider-neutral URL."""

    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix(
            "postgres://"
        )
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix(
            "postgresql://"
        )
    return SessionProvider(database_url)


@dataclass(frozen=True, slots=True)
class RuntimeComposition:
    """Application-facing runtime graph typed solely through its ports."""

    object_store: ObjectStore
    identity_store: IdentityStore
    identity_access: IdentityAccess
    access_control: AccessControl
    administration: AccessAdministration
    job_runtime: JobRuntime
    readiness: ReadinessModule


@dataclass(frozen=True, slots=True)
class RuntimeCompositionFactories:
    """Narrow construction seams for preview graph and probe tests."""

    session_provider: Callable[[str], SessionProvider] = _build_session_provider
    identity_store: Callable[[Settings, SessionProvider], IdentityStore] = (
        lambda settings, provider: SqlAlchemyIdentityStore(
            provider.session_factory,
            fingerprint_key=settings.identity_fingerprint_key.encode(),
            environment=settings.environment,
        )
    )
    identity_registry: Callable[[Settings], IdentityProviderRegistry] = (
        build_identity_registry
    )
    redis_connection: Callable[[str], Any] = Redis.from_url
    job_queue: Callable[[Any], JobQueue] = RQJobQueue.from_connection
    job_runtime: Callable[[SessionProvider, JobQueue, str], JobRuntime] = (
        lambda provider, queue, release_id: SqlAlchemyJobRuntime(
            provider.session_factory, queue=queue, release_id=release_id
        )
    )
    object_store: Callable[[Settings], ObjectStore] = build_object_store
    persistence_probe: Callable[[SessionProvider, str], PersistenceProbe] = (
        lambda provider, expected_head: PersistenceProbe.from_engine(
            provider.engine, expected_head=expected_head
        )
    )
    readiness_check: Callable[[DependencyCheckName, bool], ReadinessCheck] | None = (
        None
    )


def compose_runtime(
    *,
    settings: Settings,
    release: ReleaseManifest,
    factories: RuntimeCompositionFactories | None = None,
) -> RuntimeComposition:
    """Build local doubles or the preview's durable, concrete adapter graph."""

    if settings.environment == "local":
        return _compose_local(settings=settings, release=release)
    return _compose_preview(
        settings=settings,
        release=release,
        factories=factories or RuntimeCompositionFactories(),
    )


def _compose_local(
    *, settings: Settings, release: ReleaseManifest
) -> RuntimeComposition:
    object_store = build_object_store(settings)
    identity_store = InMemoryIdentityStore(
        fingerprint_key=settings.identity_fingerprint_key.encode()
    )
    registry = build_identity_registry(settings)
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    identity_access = IdentityAccess(
        identity_store,
        registry.identity,
        registry.email,
        environment=settings.environment,
        capture_origin=settings.identity_capture_origin,
        job_runtime=runtime,
    )
    readiness = ReadinessModule(
        surface="api",
        release_id=release.release_id,
        probes=(
            _ready_probe("runtime_config", critical=True),
            *login_dependency_probes(
                identity=lambda: _provider_readiness(
                    "identity_provider", registry.identity, settings, release.release_id
                ),
                email=lambda: _provider_readiness(
                    "email_provider", registry.email, settings, release.release_id
                ),
            ),
        ),
    )
    return _runtime_graph(
        object_store, identity_store, identity_access, runtime, readiness
    )


def _compose_preview(
    *,
    settings: Settings,
    release: ReleaseManifest,
    factories: RuntimeCompositionFactories,
) -> RuntimeComposition:
    session_provider = factories.session_provider(settings.database_url)
    identity_store = factories.identity_store(settings, session_provider)
    registry = factories.identity_registry(settings)
    redis_connection = factories.redis_connection(settings.redis_url)
    queue = factories.job_queue(redis_connection)
    runtime = factories.job_runtime(session_provider, queue, release.release_id)
    object_store = factories.object_store(settings)
    _assert_preview_adapters(
        identity_store=identity_store,
        job_queue=queue,
        job_runtime=runtime,
        object_store=object_store,
        registry=registry,
    )
    identity_access = IdentityAccess(
        identity_store,
        registry.identity,
        registry.email,
        environment=settings.environment,
        capture_origin=settings.identity_capture_origin,
        job_runtime=runtime,
    )
    def persistence() -> PersistenceProbe:
        return factories.persistence_probe(session_provider, release.database_revision)

    readiness = ReadinessModule(
        surface="api",
        release_id=release.release_id,
        probes=(
            _preview_probe("runtime_config", True, factories),
            _preview_probe("postgres", True, factories, persistence),
            _preview_probe("schema", True, factories, persistence),
            _preview_probe("postgis", True, factories, persistence),
            _preview_probe("pgvector", True, factories, persistence),
            _preview_probe("redis", True, factories, redis_connection),
            _preview_probe("object_storage", True, factories, object_store),
            *login_dependency_probes(
                identity=lambda: _provider_readiness(
                    "identity_provider", registry.identity, settings, release.release_id
                ),
                email=lambda: _provider_readiness(
                    "email_provider", registry.email, settings, release.release_id
                ),
            ),
        ),
    )
    return _runtime_graph(
        object_store, identity_store, identity_access, runtime, readiness
    )


def _runtime_graph(
    object_store: ObjectStore,
    identity_store: IdentityStore,
    identity_access: IdentityAccess,
    job_runtime: JobRuntime,
    readiness: ReadinessModule,
) -> RuntimeComposition:
    return RuntimeComposition(
        object_store=object_store,
        identity_store=identity_store,
        identity_access=identity_access,
        access_control=AccessControl(identity_store),
        administration=AccessAdministration(identity_store),
        job_runtime=job_runtime,
        readiness=readiness,
    )


def _assert_preview_adapters(
    *,
    identity_store: IdentityStore,
    job_queue: JobQueue,
    job_runtime: JobRuntime,
    object_store: ObjectStore,
    registry: IdentityProviderRegistry,
) -> None:
    """Fail startup before a preview surface can use a local/test double."""

    if (
        type(identity_store) is not SqlAlchemyIdentityStore
        or type(job_queue) is not RQJobQueue
        or type(job_runtime) is not SqlAlchemyJobRuntime
        or type(object_store) is not S3ObjectStore
        or type(registry.identity) is not SupabaseIdentityAdapter
        or type(registry.email) is not ResendEmailAdapter
        or job_runtime.queue is not job_queue
    ):
        raise ValueError("preview runtime requires durable adapters")


def _ready_probe(name: DependencyCheckName, *, critical: bool) -> ReadinessProbe:
    return ReadinessProbe(
        name=name,
        critical=critical,
        check=lambda: ReadinessCheck(name=name, state="ready", critical=critical),
    )


def _preview_probe(
    name: DependencyCheckName,
    critical: bool,
    factories: RuntimeCompositionFactories,
    dependency: object | None = None,
) -> ReadinessProbe:
    def check() -> ReadinessCheck:
        if factories.readiness_check is not None:
            return factories.readiness_check(name, critical)
        if name in {"postgres", "schema", "postgis", "pgvector"}:
            assert callable(dependency)
            return _persistence_readiness(
                cast(Literal["postgres", "schema", "postgis", "pgvector"], name),
                critical,
                cast(Callable[[], PersistenceProbe], dependency),
            )
        if name == "redis":
            return _redis_readiness(critical, dependency)
        if name == "object_storage":
            assert isinstance(dependency, S3ObjectStore)
            return _object_storage_readiness(critical, dependency)
        return ReadinessCheck(name=name, state="ready", critical=critical)

    return ReadinessProbe(name=name, critical=critical, check=check)


def _persistence_readiness(
    name: Literal["postgres", "schema", "postgis", "pgvector"],
    critical: bool,
    probe_factory: Callable[[], PersistenceProbe],
) -> ReadinessCheck:
    persistence = probe_factory().evaluate()
    source = "alembic" if name == "schema" else name
    result = persistence.checks[source]
    state: Literal["ready", "unavailable"] = (
        "ready" if result.state == "ready" else "unavailable"
    )
    return ReadinessCheck(
        name=name,
        state=state,
        critical=critical,
        code=None if state == "ready" else f"{name}.unavailable",
    )


def _redis_readiness(critical: bool, connection: object) -> ReadinessCheck:
    try:
        available = cast(Any, connection).ping()
    except Exception:
        available = False
    state: Literal["ready", "unavailable"] = "ready" if available else "unavailable"
    return ReadinessCheck(
        name="redis",
        state=state,
        critical=critical,
        code=None if state == "ready" else "redis.unavailable",
    )


def _object_storage_readiness(
    critical: bool, object_store: S3ObjectStore
) -> ReadinessCheck:
    try:
        reference = object_store.put_if_absent(
            storage_key=_MARKER_KEY,
            body=BytesIO(_MARKER_BODY),
            sha256=_MARKER_DIGEST,
            size_bytes=len(_MARKER_BODY),
            content_type="application/octet-stream",
        )
        info = object_store.stat(reference)
        available = (
            info.sha256 == _MARKER_DIGEST
            and info.size_bytes == len(_MARKER_BODY)
        )
    except Exception:
        available = False
    state: Literal["ready", "unavailable"] = "ready" if available else "unavailable"
    return ReadinessCheck(
        name="object_storage",
        state=state,
        critical=critical,
        code=None if state == "ready" else "object_storage.unavailable",
    )


def _provider_readiness(
    name: Literal["identity_provider", "email_provider"],
    provider: object,
    settings: Settings,
    release_id: str,
) -> ReadinessCheck:
    health = getattr(provider, "health", None)
    raw_state: object = health() if callable(health) else "ready"
    if raw_state in {"ready", "degraded", "unavailable"}:
        state = cast(Literal["ready", "degraded", "unavailable"], raw_state)
    else:
        state = "unavailable"
    record_dependency_metric(
        dependency=name,
        state=state,
        environment=settings.environment,
        release_id=release_id,
    )
    return ReadinessCheck(
        name=name,
        state=state,
        critical=False,
        code=None if state == "ready" else f"{name}.{state}",
    )
