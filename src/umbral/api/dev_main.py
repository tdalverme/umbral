"""Local end-to-end API entrypoint with the durable runtime.

Runs the API against a local Postgres/Redis with the real durable job runtime
and SQLAlchemy identity (like preview), but with locally reachable services and
dummy provider adapters. The magic-link flow is not usable here; sessions are
seeded with ``scripts/seed-local.py`` which prints the session cookie value.

Usage:

    uvicorn umbral.api.dev_main:app --port 8000

The worker and scheduler run with the standard local settings:

    python -m umbral.workers worker
    python -m umbral.workers scheduler
"""

from __future__ import annotations

from umbral.api.dependencies import (
    RuntimeDependencies,
    _build_agent_stack,
    _build_notifications,
    _load_release,
)
from umbral.api.main import create_app
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.runtime.composition import compose_runtime
from umbral.infrastructure.runtime.heartbeat import RuntimeHeartbeatWriter


def _dev_settings() -> Settings:
    """Preview-shaped settings pointing at local services (no provider checks)."""
    return Settings.model_validate(
        {
            "UMBRAL_ENV": "preview",
            "UMBRAL_RELEASE_ID": "dev-local",
            "UMBRAL_RELEASE_MANIFEST": "<local>",
            "UMBRAL_RELEASE_DIGEST": "sha256:" + "0" * 64,
            "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "OBJECT_STORE_BACKEND": "s3",
            "OBJECT_STORE_BUCKET": "umbral-local",
            "OBJECT_STORE_ENDPOINT_URL": "http://127.0.0.1:9000",
            "OBJECT_STORE_ACCESS_KEY": "minio_local",
            "OBJECT_STORE_SECRET_KEY": "minio_local_password",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "SENTRY_DSN": "https://dummy@example.invalid/1",
            "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
            "UMBRAL_ACCESS_MODE": "product_session",
            "IDENTITY_PROVIDER": "supabase",
            "SUPABASE_URL": "https://bpwgyvetbneghrtxcadm.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_local_dev_only",
            "IDENTITY_ISSUER": "dev-local",
            "IDENTITY_CAPTURE_ORIGIN": "http://localhost:3000",
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_dummy_local_dev_only",
            "RESEND_FROM_EMAIL": "dev@example.invalid",
            "EMAIL_WEBHOOK_SECRET": "dev-webhook-secret",
            "UMBRAL_BFF_TOKEN": "local-bff-token",
            "IDENTITY_FINGERPRINT_KEY": "local-dev-fingerprint-key",
            "SESSION_COOKIE_NAME": "umbral_local_session",
            "SESSION_SECURE": "false",
            "AGENT_MODEL_PROVIDER": "managed",
            "AGENT_MANAGED_ENDPOINT": "http://127.0.0.1:8010/v1/structured",
            "AGENT_MANAGED_API_KEY": "umbral-local-gateway",
            "AGENT_MODEL_NAME": "gpt-4.1-mini",
        }
    )


def _dependencies() -> RuntimeDependencies:
    settings = _dev_settings()
    release = _load_release(settings)
    composition = compose_runtime(settings=settings, release=release)
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
    )


app = create_app(_dependencies())
