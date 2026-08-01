"""Production composition root for durable worker and scheduler processes."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from redis import Redis

from umbral.application.identity.access import IdentityAccess
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.identity.registry import build_identity_registry
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.observability.runtime import initialize_observability
from umbral.infrastructure.queue.rq_queue import RQJobQueue
from umbral.workers.registry import JobRegistry
from umbral.workers.registry import build_identity_registry as build_job_registry


@dataclass(frozen=True, slots=True)
class ProcessDependencies:
    settings: Settings
    session_provider: SessionProvider
    identity_store: SqlAlchemyIdentityStore
    identity_access: IdentityAccess
    redis_connection: Redis[bytes]
    queue: RQJobQueue
    runtime: SqlAlchemyJobRuntime
    registry: JobRegistry
    worker_id: str

    @property
    def handlers(self) -> dict[str, object]:
        return dict(self.registry.as_mapping())


def build_process_dependencies(settings: Settings | None = None) -> ProcessDependencies:
    """Compose one real process without passing provider clients through jobs."""

    active_settings = settings or _load_settings()
    initialize_observability(active_settings)
    session_provider = SessionProvider(active_settings.database_url)
    identity_store = SqlAlchemyIdentityStore(
        session_provider.session_factory,
        fingerprint_key=active_settings.identity_fingerprint_key.encode(),
        environment=active_settings.environment,
    )
    providers = build_identity_registry(active_settings)
    identity_access = IdentityAccess(
        identity_store,
        providers.identity,
        providers.email,
        environment=active_settings.environment,
        capture_origin=active_settings.identity_capture_origin,
    )
    registry = build_job_registry(identity_access)
    redis_connection = Redis.from_url(active_settings.redis_url)
    queue = RQJobQueue.from_connection(redis_connection)
    runtime = SqlAlchemyJobRuntime(
        session_provider.session_factory,
        queue=queue,
        release_id=active_settings.release_id,
        handlers=registry.as_mapping(),
    )
    identity_access.job_runtime = runtime
    return ProcessDependencies(
        settings=active_settings,
        session_provider=session_provider,
        identity_store=identity_store,
        identity_access=identity_access,
        redis_connection=redis_connection,
        queue=queue,
        runtime=runtime,
        registry=registry,
        worker_id=f"rq:{socket.gethostname()}:{os.getpid()}",
    )


def _load_settings() -> Settings:
    values = {
        key: value
        for key, value in os.environ.items()
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
    if values:
        return Settings.from_environment(values)
    return Settings.from_environment(
        {
            "UMBRAL_ENV": "local",
            "UMBRAL_RELEASE_ID": "foundation-local",
            "UMBRAL_RELEASE_MANIFEST": "<local>",
            "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "OBJECT_STORE_BACKEND": "filesystem",
            "OBJECT_STORE_ROOT": ".umbral-local",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
        }
    )
