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
    assert settings.agent_tools_state_schema_version == 2
    assert settings.agent_tools_topology_version == 2
    assert settings.agent_tools_contract_version == "v1"
    assert settings.agent_tools_max_calls_per_turn == 5
    assert settings.agent_tools_timeout_seconds == 10.0
    assert settings.agent_tools_output_max_items == 20
    assert settings.agent_proposal_ttl_hours == 24
    assert settings.agent_chat_state_schema_version == 3
    assert settings.agent_chat_topology_version == 3
    assert settings.agent_intent_schema_version == "intent-v3"
    assert settings.agent_intent_prompt_version == "agent-intent-v1"
    assert settings.agent_reply_prompt_version == "agent-reply-v2"
    assert settings.agent_clarification_min_confidence == 0.6
    assert settings.agent_clarification_max_rounds == 2
    assert settings.agent_reply_max_refs == 10
    assert settings.agent_reply_chunk_words == 8
    assert settings.agent_evals_dataset_version == "conversations-golden-v1"
    assert settings.agent_evals_releases_version == "graph-releases-v1"
    assert settings.agent_evals_price_table_version == "price-table-v1"
    assert settings.agent_evals_gate_enabled is True
    assert settings.agent_evals_cost_threshold_pct == 20.0
    assert settings.agent_evals_latency_threshold_ms == 1500
    assert settings.agent_graph_release_id == "graph-release-001"
    assert settings.agent_budget_window_hours == 24
    assert settings.agent_budget_session_token_cap == 150000
    assert settings.agent_budget_user_token_cap == 500000
    assert settings.agent_budget_session_tool_call_cap == 40
    assert settings.agent_budget_user_cost_cap_usd == 5.0
    assert settings.agent_budget_user_concurrency_cap == 2
    assert settings.agent_budget_warning_ratio == 0.8


def test_agent_tools_overrides_are_accepted() -> None:
    values = dict(_LOCAL_BASE)
    values.update(
        {
            "AGENT_TOOLS_STATE_SCHEMA_VERSION": "3",
            "AGENT_TOOLS_TOPOLOGY_VERSION": "3",
            "AGENT_TOOLS_CONTRACT_VERSION": "v2",
            "AGENT_TOOLS_MAX_CALLS_PER_TURN": "10",
            "AGENT_TOOLS_TIMEOUT_SECONDS": "5",
            "AGENT_TOOLS_OUTPUT_MAX_ITEMS": "50",
            "AGENT_PROPOSAL_TTL_HOURS": "48",
            "AGENT_CHAT_STATE_SCHEMA_VERSION": "3",
            "AGENT_CHAT_TOPOLOGY_VERSION": "3",
            "AGENT_INTENT_SCHEMA_VERSION": "intent-v4",
            "AGENT_INTENT_PROMPT_VERSION": "agent-intent-v2",
            "AGENT_REPLY_PROMPT_VERSION": "agent-reply-v3",
            "AGENT_CLARIFICATION_MIN_CONFIDENCE": "0.8",
            "AGENT_CLARIFICATION_MAX_ROUNDS": "3",
            "AGENT_REPLY_MAX_REFS": "5",
            "AGENT_REPLY_CHUNK_WORDS": "4",
            "AGENT_EVALS_DATASET_VERSION": "conversations-golden-v2",
            "AGENT_EVALS_RELEASES_VERSION": "graph-releases-v2",
            "AGENT_EVALS_PRICE_TABLE_VERSION": "price-table-v2",
            "AGENT_EVALS_GATE_ENABLED": "false",
            "AGENT_EVALS_COST_THRESHOLD_PCT": "30",
            "AGENT_EVALS_LATENCY_THRESHOLD_MS": "3000",
            "AGENT_GRAPH_RELEASE_ID": "graph-release-002",
            "AGENT_BUDGET_WINDOW_HOURS": "48",
            "AGENT_BUDGET_SESSION_TOKEN_CAP": "100000",
            "AGENT_BUDGET_USER_TOKEN_CAP": "300000",
            "AGENT_BUDGET_SESSION_TOOL_CALL_CAP": "20",
            "AGENT_BUDGET_USER_COST_CAP_USD": "10",
            "AGENT_BUDGET_USER_CONCURRENCY_CAP": "3",
            "AGENT_BUDGET_WARNING_RATIO": "0.9",
        }
    )
    settings = Settings.from_environment(values)
    assert settings.agent_tools_state_schema_version == 3
    assert settings.agent_tools_topology_version == 3
    assert settings.agent_tools_contract_version == "v2"
    assert settings.agent_tools_max_calls_per_turn == 10
    assert settings.agent_tools_timeout_seconds == 5.0
    assert settings.agent_tools_output_max_items == 50
    assert settings.agent_proposal_ttl_hours == 48
    assert settings.agent_chat_state_schema_version == 3
    assert settings.agent_chat_topology_version == 3
    assert settings.agent_intent_schema_version == "intent-v4"
    assert settings.agent_intent_prompt_version == "agent-intent-v2"
    assert settings.agent_reply_prompt_version == "agent-reply-v3"
    assert settings.agent_clarification_min_confidence == 0.8
    assert settings.agent_clarification_max_rounds == 3
    assert settings.agent_reply_max_refs == 5
    assert settings.agent_reply_chunk_words == 4
    assert settings.agent_evals_dataset_version == "conversations-golden-v2"
    assert settings.agent_evals_releases_version == "graph-releases-v2"
    assert settings.agent_evals_price_table_version == "price-table-v2"
    assert settings.agent_evals_gate_enabled is False
    assert settings.agent_evals_cost_threshold_pct == 30.0
    assert settings.agent_evals_latency_threshold_ms == 3000
    assert settings.agent_graph_release_id == "graph-release-002"
    assert settings.agent_budget_window_hours == 48
    assert settings.agent_budget_session_token_cap == 100000
    assert settings.agent_budget_user_token_cap == 300000
    assert settings.agent_budget_session_tool_call_cap == 20
    assert settings.agent_budget_user_cost_cap_usd == 10.0
    assert settings.agent_budget_user_concurrency_cap == 3
    assert settings.agent_budget_warning_ratio == 0.9


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
