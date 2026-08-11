"""Notification settings config tests (H5)."""

from __future__ import annotations

from umbral.infrastructure.config.settings import Settings

_BASE = {
    "UMBRAL_ENV": "local",
    "UMBRAL_RELEASE_ID": "foundation-local",
    "UMBRAL_RELEASE_MANIFEST": ".data/release-manifest.local.json",
    "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "OBJECT_STORE_BACKEND": "filesystem",
    "OBJECT_STORE_ROOT": ".data/objects",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
    "UMBRAL_API_BASE_URL": "http://localhost:8000",
}


def test_notification_settings_defaults() -> None:
    settings = Settings.from_environment(_BASE)
    assert settings.notifications_enabled is True
    assert settings.notifications_policy_version == "notification-policy-v1"
    assert settings.notifications_planner_dataset_version == "planner-golden-v1"
    assert settings.notifications_unsubscribe_ttl_hours == 24
    assert settings.notifications_default_timezone == "America/Argentina/Buenos_Aires"


def test_notification_settings_override() -> None:
    values = dict(_BASE)
    values["NOTIFICATIONS_ENABLED"] = "false"
    values["NOTIFICATIONS_EMAIL_FROM"] = "alerta@test"
    values["NOTIFICATIONS_UNSUBSCRIBE_TTL_HOURS"] = "6"
    settings = Settings.from_environment(values)
    assert settings.notifications_enabled is False
    assert settings.notifications_email_from == "alerta@test"
    assert settings.notifications_unsubscribe_ttl_hours == 6


def test_notification_settings_reject_unknown() -> None:
    from umbral.infrastructure.config.settings import SettingsValidationError

    values = dict(_BASE)
    values["NOTIFICATIONS_MADE_UP"] = "x"
    try:
        Settings.from_environment(values)
    except SettingsValidationError as error:
        assert error.field_name == "NOTIFICATIONS_MADE_UP"
    else:
        raise AssertionError("expected SettingsValidationError")
