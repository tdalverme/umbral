from __future__ import annotations

import pytest

from umbral.infrastructure.config.settings import Settings, SettingsValidationError
from umbral.infrastructure.identity.registry import build_identity_registry


def _preview_settings(*, origin: str) -> Settings:
    return Settings.from_environment(
        {
            "UMBRAL_ENV": "preview",
            "UMBRAL_RELEASE_ID": "preview-test",
            "UMBRAL_RELEASE_MANIFEST": "/run/secrets/release.json",
            "UMBRAL_RELEASE_DIGEST": "sha256:" + "a" * 64,
            "DATABASE_URL": "postgresql://user:pass@db.preview.invalid/app",
            "REDIS_URL": "redis://redis.railway.internal/0",
            "OBJECT_STORE_BACKEND": "s3",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.preview.invalid",
            "SENTRY_DSN": "https://sentry.invalid/1",
            "UMBRAL_API_BASE_URL": "http://api.railway.internal:8000",
            "UMBRAL_ACCESS_MODE": "product_session",
            "IDENTITY_PROVIDER": "supabase",
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test_value",
            "IDENTITY_ISSUER": "https://project.supabase.co/auth/v1",
            "IDENTITY_CAPTURE_ORIGIN": origin,
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_test_value",
            "RESEND_FROM_EMAIL": "Umbral <onboarding@resend.dev>",
            "EMAIL_WEBHOOK_SECRET": "whsec_test_value",
        }
    )


def test_provider_registry_keeps_environment_redirect_allowlist() -> None:
    registry = build_identity_registry(
        _preview_settings(origin="https://preview.umbral.invalid")
    )
    registry.policy.assert_capture_url("https://preview.umbral.invalid/auth/capture?x=1")
    with pytest.raises(ValueError):
        registry.policy.assert_capture_url("https://production.umbral.invalid/auth/capture")


def test_production_rejects_non_host_cookie_when_identity_settings_are_present(
) -> None:
    values = {
        "UMBRAL_ENV": "production",
        "UMBRAL_RELEASE_ID": "production-test",
        "UMBRAL_RELEASE_MANIFEST": "/run/secrets/release.json",
        "UMBRAL_RELEASE_DIGEST": "sha256:" + "a" * 64,
        "DATABASE_URL": "postgresql://user:pass@db.production.invalid/app",
        "REDIS_URL": "rediss://redis.production.invalid/0",
        "OBJECT_STORE_BACKEND": "s3",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.production.invalid",
        "SENTRY_DSN": "https://sentry.invalid/1",
        "UMBRAL_API_BASE_URL": "https://api.production.internal.invalid",
        "UMBRAL_ACCESS_AUDIENCE": "production",
        "IDENTITY_CAPTURE_ORIGIN": "https://umbral.invalid",
        "IDENTITY_FINGERPRINT_KEY": "production-fingerprint-key",
        "UMBRAL_BFF_TOKEN": "production-bff-token",
        "SESSION_COOKIE_NAME": "umbral_session",
        "SESSION_SECURE": "true",
    }
    with pytest.raises(SettingsValidationError) as error:
        Settings.from_environment(values)
    assert error.value.rule_code == "CONFIG_COOKIE_NAME"
