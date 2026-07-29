from __future__ import annotations

import pytest

from umbral.infrastructure.config.settings import Settings, SettingsValidationError
from umbral.infrastructure.identity.registry import build_identity_registry


def _settings(environment: str, *, origin: str) -> Settings:
    return Settings.model_validate(
        {
            "UMBRAL_ENV": environment,
            "UMBRAL_RELEASE_ID": f"{environment}-test",
            "UMBRAL_RELEASE_MANIFEST": "<local>",
            "DATABASE_URL": "postgresql://user:pass@db.invalid/app",
            "REDIS_URL": "redis://redis.invalid/0",
            "OBJECT_STORE_BACKEND": "filesystem",
            "OBJECT_STORE_ROOT": ".data",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel.invalid",
            "UMBRAL_API_BASE_URL": "http://api.invalid",
            "IDENTITY_PROVIDER": "fake",
            "IDENTITY_ISSUER": f"fake://{environment}",
            "IDENTITY_CAPTURE_ORIGIN": origin,
            "EMAIL_PROVIDER": "recording",
        }
    )


def test_provider_registry_keeps_environment_redirect_allowlist() -> None:
    registry = build_identity_registry(
        _settings("preview", origin="https://preview.umbral.invalid")
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
