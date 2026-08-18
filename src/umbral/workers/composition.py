"""Production composition root for durable worker and scheduler processes."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from redis import Redis

from umbral.application.identity.access import IdentityAccess
from umbral.application.ingestion.contracts import ImportRunSnapshot
from umbral.application.ingestion.service import ImportRunService
from umbral.application.runtime.version import (
    ReleaseManifest,
    load_release_manifest,
    parse_release_manifest,
)
from umbral.infrastructure.agent.checkpointer import (
    close_postgres_saver,
    create_postgres_saver,
)
from umbral.infrastructure.agent.proposals.expire import (
    expire_search_profile_proposals,
)
from umbral.infrastructure.agent.purge import (
    PostgresThreadStore,
    SqlAlchemyStaleSessionFinder,
    purge_agent_checkpoints,
)
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.criteria.composition import build_criteria_service
from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.identity.registry import build_identity_registry
from umbral.infrastructure.ingestion.composition import build_ingestion_service
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.notifications.composition import (
    build_notification_services,
)
from umbral.infrastructure.object_store.factory import build_object_store
from umbral.infrastructure.observability.runtime import initialize_observability
from umbral.infrastructure.queue.rq_queue import RQJobQueue
from umbral.infrastructure.radar.composition import build_radar_service
from umbral.infrastructure.runtime.heartbeat import RuntimeHeartbeatWriter
from umbral.infrastructure.scoring.composition import build_scoring_service
from umbral.infrastructure.silver.composition import build_normalize_service
from umbral.workers.criteria import build_criteria_registry
from umbral.workers.imports import build_ingestion_registry
from umbral.workers.notifications import (
    build_digest_duty,
    build_notifications_registry,
    build_plan_duty,
)
from umbral.workers.radar import build_radar_registry
from umbral.workers.registry import JobRegistry
from umbral.workers.registry import build_identity_registry as build_job_registry
from umbral.workers.silver import build_silver_registry, normalize_publisher
from umbral.workers.urban import build_urban_registry


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
    ingestion: ImportRunService = field(default=None)  # type: ignore[assignment]
    heartbeat_writer: RuntimeHeartbeatWriter | None = None
    agent_checkpoint_purge: Callable[[datetime], int] | None = None
    proposal_expire: Callable[[datetime], int] | None = None
    notifications_plan: Callable[[datetime], int] | None = None
    notifications_digest: Callable[[datetime], int] | None = None

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
    object_store = build_object_store(active_settings)
    ingestion = build_ingestion_service(
        session_factory=session_provider.session_factory,
        object_store=object_store,
    )
    silver = build_normalize_service(
        session_factory=session_provider.session_factory,
        geocoding_enabled=active_settings.silver_geocoding_enabled,
        geocoding_endpoint=active_settings.silver_geocoding_endpoint,
        geocoding_cache_size=active_settings.silver_geocoding_cache_size,
        geocoding_rate_limit=active_settings.silver_geocoding_rate_limit,
    )
    for handler in build_silver_registry(silver).as_mapping().values():
        registry.register(handler)
    scoring = build_scoring_service(
        session_factory=session_provider.session_factory,
        policy_seed_version=active_settings.scoring_policy_seed_version,
        legacy_score_policy_version=active_settings.scoring_legacy_score_policy_version,
        comparison_max_listings=active_settings.scoring_comparison_max_listings,
        comparator_enabled=active_settings.scoring_comparator_enabled,
    )
    radar = build_radar_service(
        session_factory=session_provider.session_factory,
        job_runtime=None,
        policy_engine=scoring,
        score_policy_version=active_settings.scoring_policy_seed_version,
    )
    for handler in build_radar_registry(radar).as_mapping().values():
        registry.register(handler)
    criteria = build_criteria_service(
        session_factory=session_provider.session_factory,
        job_runtime=None,
        extraction_provider=active_settings.extraction_provider,
        extraction_endpoint=None,
        extraction_api_key=active_settings.extraction_managed_api_key,
        extraction_model=active_settings.extraction_managed_model,
        qualitative_max_attempts=active_settings.criteria_qualitative_max_attempts,
        batch_size=active_settings.criteria_batch_size,
        extraction_job_type=active_settings.criteria_extraction_job_type,
        recompute_job_type=active_settings.criteria_recompute_job_type,
        embeddings_enabled=active_settings.embeddings_enabled,
        embedding_model_version_key=active_settings.embeddings_model_version_key,
        urban_context_enabled=active_settings.urban_context_enabled,
    )
    for handler in build_criteria_registry(criteria).as_mapping().values():
        registry.register(handler)
    for handler in build_urban_registry(
        session_provider.session_factory
    ).as_mapping().values():
        registry.register(handler)
    normalize_publish = _late_bind_publisher()
    for handler in (
        build_ingestion_registry(ingestion, normalize_publish).as_mapping().values()
    ):
        registry.register(handler)
    events_out = SqlAlchemyEventRepository(session_provider.session_factory)
    notifications = build_notification_services(
        settings=active_settings,
        session_provider=session_provider,
        events_out=events_out,
    )
    for handler in build_notifications_registry(
        notifications.delivery
    ).as_mapping().values():
        registry.register(handler)
    redis_connection = Redis.from_url(active_settings.redis_url)
    queue = RQJobQueue.from_connection(redis_connection)
    runtime = SqlAlchemyJobRuntime(
        session_provider.session_factory,
        queue=queue,
        release_id=active_settings.release_id,
        handlers=registry.as_mapping(),
    )
    normalize_publish.bind(runtime)
    identity_access.job_runtime = runtime
    heartbeat_writer = None
    if active_settings.environment != "local":
        heartbeat_writer = RuntimeHeartbeatWriter(
            session_provider.session_factory,
            environment=active_settings.environment,
            release=_load_release(active_settings),
        )
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
        ingestion=ingestion,
        heartbeat_writer=heartbeat_writer,
        agent_checkpoint_purge=_build_agent_purge(active_settings),
        proposal_expire=_build_proposal_expire(active_settings),
        notifications_plan=build_plan_duty(notifications.planner),
        notifications_digest=build_digest_duty(notifications.planner),
    )


def _build_proposal_expire(settings: Settings) -> Callable[[datetime], int]:
    """Build the scheduler maintenance duty that expires pending proposals."""

    def expire(now: datetime) -> int:
        session_factory = SessionProvider(settings.database_url).session_factory
        return expire_search_profile_proposals(
            session_factory,
            ttl_hours=settings.agent_proposal_ttl_hours,
            now=now,
        )

    return expire


def _build_agent_purge(settings: Settings) -> Callable[[datetime], int]:
    """Build the scheduler maintenance duty that purges expired checkpoints."""

    def purge(now: datetime) -> int:
        session_factory = SessionProvider(settings.database_url).session_factory
        finder = SqlAlchemyStaleSessionFinder(session_factory)
        saver = create_postgres_saver(
            settings.database_url, strict_msgpack=settings.agent_strict_msgpack
        )
        try:
            return purge_agent_checkpoints(
                finder=finder,
                threads=PostgresThreadStore(saver),
                retention_days=settings.agent_checkpoint_retention_days,
                now=now,
            )
        finally:
            close_postgres_saver(saver)

    return purge


class _LateBindPublisher:
    """Publishes the chained normalize job once the runtime is available."""

    def __init__(self) -> None:
        self._runtime: SqlAlchemyJobRuntime | None = None

    def bind(self, runtime: SqlAlchemyJobRuntime) -> None:
        self._runtime = runtime

    def __call__(self, snapshot: ImportRunSnapshot) -> None:
        if self._runtime is None:
            return
        normalize_publisher(self._runtime)(snapshot)


def _late_bind_publisher() -> _LateBindPublisher:
    return _LateBindPublisher()


def _load_release(settings: Settings) -> ReleaseManifest:
    value = settings.release_manifest
    if value.lstrip().startswith("{"):
        return parse_release_manifest(value)
    return load_release_manifest(Path(value))


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
                "SILVER_",
                "CRITERIA_",
                "SCORING_",
                "LEARNING_",
                "FEEDBACK_",
                "EMBEDDINGS_",
                "URBAN_",
                "NOTIFICATIONS_",
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
