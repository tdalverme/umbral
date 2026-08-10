"""Agent/chat settings registration and defaults (T005, R-08)."""

from __future__ import annotations

import pytest

from umbral.infrastructure.config.settings import Settings, SettingsValidationError

_LOCAL_BASE = {
    "UMBRAL_ENV": "local",
    "UMBRAL_RELEASE_ID": "test",
    "UMBRAL_RELEASE_MANIFEST": "<local>",
    "DATABASE_URL": "postgresql://u:p@127.0.0.1/db",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
    "OBJECT_STORE_BACKEND": "filesystem",
    "OBJECT_STORE_ROOT": ".umbral-local",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
    "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
}


def test_agent_settings_have_safe_defaults() -> None:
    settings = Settings.from_environment(dict(_LOCAL_BASE))
    assert settings.agent_model_provider == "fake"
    assert settings.agent_model_name == "local-fake"
    assert settings.agent_model_timeout_seconds == 30.0
    assert settings.agent_model_max_retries == 2
    assert settings.agent_state_schema_version == 1
    assert settings.agent_graph_topology_version == 1
    assert settings.agent_checkpoint_retention_days == 30
    assert settings.agent_strict_msgpack is True
    assert settings.chat_message_max_length == 4000


def test_agent_overrides_are_accepted() -> None:
    values = dict(_LOCAL_BASE)
    values.update(
        {
            "AGENT_MODEL_PROVIDER": "managed",
            "AGENT_MODEL_TIMEOUT_SECONDS": "15",
            "AGENT_MODEL_MAX_RETRIES": "0",
            "AGENT_CHECKPOINT_RETENTION_DAYS": "7",
            "AGENT_STRICT_MSGPACK": "false",
            "CHAT_MESSAGE_MAX_LENGTH": "2000",
            "AGENT_MANAGED_ENDPOINT": "https://provider.invalid/v1",
            "AGENT_MANAGED_API_KEY": "secret",
        }
    )
    settings = Settings.from_environment(values)
    assert settings.agent_model_provider == "managed"
    assert settings.agent_model_timeout_seconds == 15.0
    assert settings.agent_model_max_retries == 0
    assert settings.agent_checkpoint_retention_days == 7
    assert settings.agent_strict_msgpack is False
    assert settings.chat_message_max_length == 2000


def test_unknown_agent_setting_is_rejected() -> None:
    values = dict(_LOCAL_BASE)
    values["AGENT_NOT_A_SETTING"] = "x"
    with pytest.raises(SettingsValidationError) as excinfo:
        Settings.from_environment(values)
    assert excinfo.value.rule_code == "CONFIG_UNKNOWN_SETTING"
