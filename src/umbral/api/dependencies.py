"""Composition-time dependencies for the API runtime surface."""
# ruff: noqa: E501

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from umbral.application.feedback.service import FeedbackService
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.ports import IdentityStore
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.ports import JobRuntime
from umbral.application.objects.ports import ObjectStore
from umbral.application.playground.service import PlaygroundService
from umbral.application.radar.service import RadarService
from umbral.application.runtime.readiness import ReadinessModule
from umbral.application.runtime.version import (
    ReleaseArtifact,
    ReleaseManifest,
    load_release_manifest,
    parse_release_manifest,
)
from umbral.application.scoring.service import ScoringService
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.notifications.composition import (
    NotificationServices,
    build_notification_services,
)
from umbral.infrastructure.runtime.composition import (
    RuntimeCompositionFactories,
    compose_runtime,
)
from umbral.infrastructure.runtime.heartbeat import RuntimeHeartbeatWriter


def _build_notifications(settings: Settings) -> NotificationServices | None:
    if not settings.notifications_enabled:
        return None
    session_provider = SessionProvider(settings.database_url)
    return build_notification_services(
        settings=settings,
        session_provider=session_provider,
        events_out=SqlAlchemyEventRepository(session_provider.session_factory),
    )


def _build_agent_stack(
    settings: Settings, composition: object
) -> dict[str, object]:
    """Compose the production agent stack when the chat surface is present.

    A Postgres outage keeps the API importable (chat stays unconfigured,
    consistent with degraded readiness); other failures propagate.
    """
    if getattr(settings, "agent_model_provider", None) is None:
        return {}
    session_provider = SessionProvider(settings.database_url)
    from umbral.agent.runtime import ChatRuntime
    from umbral.infrastructure.agent.production import build_production_stack

    try:
        stack = build_production_stack(
            settings=settings,
            session_factory=session_provider.session_factory,
            database_url=settings.database_url,
            radar=getattr(composition, "radar", None),
            scoring=getattr(composition, "scoring", None),
            feedback=getattr(composition, "feedback", None),
            criteria=getattr(composition, "criteria", None),
        )
        runtime = ChatRuntime(
            graph=stack.graph,  # type: ignore[arg-type]
            conversation=stack.chat,
            runs=stack.graph_runs,
        )
    except Exception:  # noqa: BLE001 - Postgres down locally degrades the chat
        if getattr(settings, "environment", "local") != "local":
            raise
        return {}
    return {
        "chat": stack.chat,
        "agent_runtime": runtime,
        "proposals": stack.proposals,
        "graph_runs": stack.graph_runs,
        "ops_overview": _build_ops_overview(settings),
    }


def _build_preference_service(settings: Settings) -> dict[str, object]:
    """Compose the durable preference service over the real repositories."""
    session_provider = SessionProvider(settings.database_url)
    from umbral.application.preferences.contracts import (
        PreferenceConcept,
        PreferencePolicySpec,
    )
    from umbral.application.preferences.service import PreferenceService
    from umbral.infrastructure.db.repositories.criteria import (
        SqlAlchemyConceptRepository,
    )
    from umbral.infrastructure.db.repositories.preferences import (
        SqlAlchemyBindingRepository,
        SqlAlchemyExpressionRepository,
    )

    expressions = SqlAlchemyExpressionRepository(session_provider.session_factory)
    bindings = SqlAlchemyBindingRepository(session_provider.session_factory)
    concepts = SqlAlchemyConceptRepository(session_provider.session_factory)

    class _ConceptReader:
        def get(self, key: str) -> PreferenceConcept | None:
            concept = concepts.get(key)
            if concept is None:
                return None
            return PreferenceConcept(
                key=concept.key,
                matcher_type=concept.matcher_type,
                computable=bool(
                    (concept.compute_policy or {}).get("computable", False)
                ),
            )

    service = PreferenceService(
        expressions=expressions,
        bindings=bindings,
        mutations=expressions,
        concepts=_ConceptReader(),
        policy=PreferencePolicySpec.v1(),
    )
    return {"preferences": service}


def _build_ops_overview(settings: Settings) -> object:
    from umbral.application.agent_evals.price import load_price_table
    from umbral.application.agent_ops.service import OpsOverviewService
    from umbral.infrastructure.agent_ops.overview import (
        SqlAlchemyOpsRunRepository,
    )

    price_table = load_price_table(
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "agent-evals"
        / "v1"
        / "price-table-v1.json"
    )
    return OpsOverviewService(
        SqlAlchemyOpsRunRepository(
            SessionProvider(settings.database_url).session_factory,
            price_table,
        )
    )

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
    scoring: ScoringService | None = None
    feedback: FeedbackService | None = None
    heartbeat_writer: RuntimeHeartbeatWriter | None = None
    job_runtime: JobRuntime | None = None
    chat: object | None = None
    agent_runtime: object | None = None
    proposals: object | None = None
    graph_runs: object | None = None
    ops_overview: object | None = None
    notifications: object | None = None
    preferences: object | None = None
    playground: PlaygroundService | None = None


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
        scoring=composition.scoring,
        feedback=composition.feedback,
        heartbeat_writer=heartbeat_writer,
        job_runtime=composition.job_runtime,
        notifications=_build_notifications(settings),
        **_build_agent_stack(settings, composition),
        **_build_preference_service(settings),
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
                "SILVER_",
                "CRITERIA_",
                "SCORING_",
                "LEARNING_",
                "FEEDBACK_",
                "EMBEDDINGS_",
                "URBAN_",
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
