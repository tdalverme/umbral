"""API composition configuration behavior."""

from __future__ import annotations

import pytest

from umbral.api.dependencies import _load_settings, build_runtime_dependencies
from umbral.infrastructure.config.settings import SettingsValidationError


def test_runtime_dependencies_reject_unknown_runtime_environment_settings() -> None:
    with pytest.raises(SettingsValidationError) as raised:
        build_runtime_dependencies({"UMBRAL_UNDECLARED_OPTION": "enabled"})

    assert raised.value.rule_code == "CONFIG_UNKNOWN_SETTING"
    assert raised.value.field_name == "UMBRAL_UNDECLARED_OPTION"


def test_runtime_settings_loader_preserves_preview_supabase_configuration() -> None:
    settings = _load_settings(
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
            "SUPABASE_URL": "https://bpwgyvetbneghrtxcadm.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test_value",
            "IDENTITY_ISSUER": "https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
            "IDENTITY_CAPTURE_ORIGIN": "https://preview.umbral.invalid",
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_test_value",
            "RESEND_FROM_EMAIL": "Umbral <onboarding@resend.dev>",
            "EMAIL_WEBHOOK_SECRET": "whsec_test_value",
        }
    )

    assert settings.supabase_url == "https://bpwgyvetbneghrtxcadm.supabase.co"
