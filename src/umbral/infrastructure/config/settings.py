"""Safe, explicit configuration validation for runtime surfaces."""
# ruff: noqa: E501

from __future__ import annotations

import re
from typing import ClassVar, Literal, Mapping
from urllib.parse import ParseResult, urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "preview", "production"]
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}$")
_SUPABASE_PROJECT_HOST = "bpwgyvetbneghrtxcadm.supabase.co"
_REQUIRED_FIELDS = (
    "UMBRAL_ENV",
    "UMBRAL_RELEASE_ID",
    "UMBRAL_RELEASE_MANIFEST",
    "DATABASE_URL",
    "REDIS_URL",
    "OBJECT_STORE_BACKEND",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "UMBRAL_API_BASE_URL",
)


class SettingsValidationError(ValueError):
    """A startup diagnostic that carries a field and rule, never its value."""

    def __init__(self, rule_code: str, field_name: str) -> None:
        self.rule_code = rule_code
        self.field_name = field_name
        super().__init__(f"{rule_code}: {field_name}")


class Settings(BaseSettings):
    """The single configuration inventory accepted by the Python runtime."""

    model_config = SettingsConfigDict(extra="forbid", case_sensitive=True)

    environment: Environment = Field(validation_alias="UMBRAL_ENV")
    release_id: str = Field(validation_alias="UMBRAL_RELEASE_ID")
    release_manifest: str = Field(validation_alias="UMBRAL_RELEASE_MANIFEST")
    release_digest: str | None = Field(
        default=None, validation_alias="UMBRAL_RELEASE_DIGEST"
    )
    database_url: str = Field(validation_alias="DATABASE_URL")
    redis_url: str = Field(validation_alias="REDIS_URL")
    object_store_backend: Literal["filesystem", "s3"] = Field(
        validation_alias="OBJECT_STORE_BACKEND"
    )
    object_store_root: str | None = Field(
        default=None, validation_alias="OBJECT_STORE_ROOT"
    )
    object_store_bucket: str | None = Field(
        default=None, validation_alias="OBJECT_STORE_BUCKET"
    )
    object_store_endpoint_url: str | None = Field(
        default=None, validation_alias="OBJECT_STORE_ENDPOINT_URL"
    )
    object_store_access_key: str | None = Field(
        default=None, validation_alias="OBJECT_STORE_ACCESS_KEY"
    )
    object_store_secret_key: str | None = Field(
        default=None, validation_alias="OBJECT_STORE_SECRET_KEY"
    )
    otel_exporter_otlp_endpoint: str = Field(
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_exporter_otlp_headers: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_HEADERS",
        repr=False,
    )
    otel_exporter_otlp_traces_endpoint: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    )
    otel_exporter_otlp_traces_headers: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        repr=False,
    )
    otel_exporter_otlp_metrics_endpoint: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    )
    otel_exporter_otlp_metrics_headers: str | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_METRICS_HEADERS",
        repr=False,
    )
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    api_base_url: str = Field(validation_alias="UMBRAL_API_BASE_URL")
    access_mode: Literal["product_session", "cloudflare"] = Field(
        default="cloudflare", validation_alias="UMBRAL_ACCESS_MODE"
    )
    access_audience: str | None = Field(
        default=None, validation_alias="UMBRAL_ACCESS_AUDIENCE"
    )
    identity_provider: str = Field(default="fake", validation_alias="IDENTITY_PROVIDER")
    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_secret_key: str | None = Field(
        default=None, validation_alias="SUPABASE_SECRET_KEY"
    )
    identity_issuer: str = Field(
        default="fake://local", validation_alias="IDENTITY_ISSUER"
    )
    identity_capture_origin: str = Field(
        default="http://localhost:3000", validation_alias="IDENTITY_CAPTURE_ORIGIN"
    )
    email_provider: str = Field(default="recording", validation_alias="EMAIL_PROVIDER")
    resend_api_key: str | None = Field(default=None, validation_alias="RESEND_API_KEY")
    resend_from_email: str | None = Field(
        default=None, validation_alias="RESEND_FROM_EMAIL"
    )
    email_webhook_secret: str | None = Field(
        default=None, validation_alias="EMAIL_WEBHOOK_SECRET"
    )
    bff_token: str = Field(
        default="local-bff-token", validation_alias="UMBRAL_BFF_TOKEN"
    )
    identity_fingerprint_key: str = Field(
        default="local-identity-fingerprint-key",
        validation_alias="IDENTITY_FINGERPRINT_KEY",
    )
    session_cookie_name: str = Field(
        default="__Host-umbral_session", validation_alias="SESSION_COOKIE_NAME"
    )
    session_secure: bool = Field(default=True, validation_alias="SESSION_SECURE")
    silver_geocoding_enabled: bool = Field(
        default=False, validation_alias="SILVER_GEOCODING_ENABLED"
    )
    silver_geocoding_endpoint: str | None = Field(
        default=None, validation_alias="SILVER_GEOCODING_ENDPOINT"
    )
    silver_geocoding_cache_size: int = Field(
        default=512, validation_alias="SILVER_GEOCODING_CACHE_SIZE"
    )
    silver_geocoding_rate_limit: float = Field(
        default=1.0, validation_alias="SILVER_GEOCODING_RATE_LIMIT"
    )
    radar_page_size_default: int = Field(
        default=25, validation_alias="RADAR_PAGE_SIZE_DEFAULT"
    )
    radar_page_size_max: int = Field(
        default=100, validation_alias="RADAR_PAGE_SIZE_MAX"
    )
    radar_run_job_type: str = Field(
        default="recommendation.run", validation_alias="RADAR_RUN_JOB_TYPE"
    )
    radar_score_policy_version: str = Field(
        default="scoring-baseline-v1", validation_alias="RADAR_SCORE_POLICY_VERSION"
    )
    radar_run_poll_interval_seconds: int = Field(
        default=3, validation_alias="RADAR_RUN_POLL_INTERVAL_SECONDS"
    )
    criteria_seed_version: str = Field(
        default="concepts-v1", validation_alias="CRITERIA_SEED_VERSION"
    )
    criteria_qualitative_max_attempts: int = Field(
        default=2, validation_alias="CRITERIA_QUALITATIVE_MAX_ATTEMPTS"
    )
    criteria_batch_size: int = Field(
        default=250, validation_alias="CRITERIA_BATCH_SIZE"
    )
    criteria_extraction_job_type: str = Field(
        default="extraction.run", validation_alias="CRITERIA_EXTRACTION_JOB_TYPE"
    )
    criteria_recompute_job_type: str = Field(
        default="extraction.recompute", validation_alias="CRITERIA_RECOMPUTE_JOB_TYPE"
    )
    extraction_provider: str = Field(
        default="fake", validation_alias="EXTRACTION_PROVIDER"
    )
    extraction_managed_model: str | None = Field(
        default=None, validation_alias="EXTRACTION_MANAGED_MODEL"
    )
    extraction_managed_api_key: str | None = Field(
        default=None,
        validation_alias="EXTRACTION_MANAGED_API_KEY",
        repr=False,
    )
    embeddings_enabled: bool = Field(
        default=False, validation_alias="EMBEDDINGS_ENABLED"
    )
    embeddings_dimension: int = Field(
        default=1536, validation_alias="EMBEDDINGS_DIMENSION"
    )
    embeddings_model_version_key: str | None = Field(
        default=None, validation_alias="EMBEDDINGS_MODEL_VERSION_KEY"
    )
    urban_context_enabled: bool = Field(
        default=False, validation_alias="URBAN_CONTEXT_ENABLED"
    )
    urban_source_limits: str | None = Field(
        default=None, validation_alias="URBAN_SOURCE_LIMITS"
    )
    scoring_policy_seed_version: str = Field(
        default="scoring-policy-v1", validation_alias="SCORING_POLICY_SEED_VERSION"
    )
    scoring_legacy_score_policy_version: str = Field(
        default="scoring-baseline-v1",
        validation_alias="SCORING_LEGACY_SCORE_POLICY_VERSION",
    )
    scoring_comparison_max_listings: int = Field(
        default=6, validation_alias="SCORING_COMPARISON_MAX_LISTINGS"
    )
    scoring_comparator_enabled: bool = Field(
        default=False, validation_alias="SCORING_COMPARATOR_ENABLED"
    )
    scoring_explanations_copy_contract_version: str = Field(
        default="1", validation_alias="SCORING_EXPLANATIONS_COPY_CONTRACT_VERSION"
    )
    learning_policy_seed_version: str = Field(
        default="learning-v1", validation_alias="LEARNING_POLICY_SEED_VERSION"
    )
    feedback_quick_reasons_seed_version: str = Field(
        default="quick-reasons-v1",
        validation_alias="FEEDBACK_QUICK_REASONS_SEED_VERSION",
    )
    feedback_free_feedback_enabled: bool = Field(
        default=False, validation_alias="FEEDBACK_FREE_FEEDBACK_ENABLED"
    )
    feedback_max_free_feedback_length: int = Field(
        default=500, validation_alias="FEEDBACK_MAX_FREE_FEEDBACK_LENGTH"
    )
    matching_golden_dataset_version: str = Field(
        default="golden-dataset-v1",
        validation_alias="MATCHING_GOLDEN_DATASET_VERSION",
    )
    matching_regression_gate_enabled: bool = Field(
        default=True, validation_alias="MATCHING_REGRESSION_GATE_ENABLED"
    )
    agent_model_provider: str = Field(
        default="fake", validation_alias="AGENT_MODEL_PROVIDER"
    )
    agent_model_name: str = Field(
        default="local-fake", validation_alias="AGENT_MODEL_NAME"
    )
    agent_model_timeout_seconds: float = Field(
        default=30.0, validation_alias="AGENT_MODEL_TIMEOUT_SECONDS"
    )
    agent_model_max_retries: int = Field(
        default=2, validation_alias="AGENT_MODEL_MAX_RETRIES"
    )
    agent_managed_endpoint: str | None = Field(
        default=None, validation_alias="AGENT_MANAGED_ENDPOINT"
    )
    agent_managed_api_key: str | None = Field(
        default=None,
        validation_alias="AGENT_MANAGED_API_KEY",
        repr=False,
    )
    agent_state_schema_version: int = Field(
        default=1, validation_alias="AGENT_STATE_SCHEMA_VERSION"
    )
    agent_graph_topology_version: int = Field(
        default=1, validation_alias="AGENT_GRAPH_TOPOLOGY_VERSION"
    )
    agent_prompt_version: str = Field(
        default="agent-chat-v1", validation_alias="AGENT_PROMPT_VERSION"
    )
    agent_reply_schema_version: str = Field(
        default="reply-v1", validation_alias="AGENT_REPLY_SCHEMA_VERSION"
    )
    agent_checkpoint_retention_days: int = Field(
        default=30, validation_alias="AGENT_CHECKPOINT_RETENTION_DAYS"
    )
    agent_strict_msgpack: bool = Field(
        default=True, validation_alias="AGENT_STRICT_MSGPACK"
    )
    chat_message_max_length: int = Field(
        default=4000, validation_alias="CHAT_MESSAGE_MAX_LENGTH"
    )
    agent_tools_state_schema_version: int = Field(
        default=2, validation_alias="AGENT_TOOLS_STATE_SCHEMA_VERSION"
    )
    agent_tools_topology_version: int = Field(
        default=2, validation_alias="AGENT_TOOLS_TOPOLOGY_VERSION"
    )
    agent_tools_contract_version: str = Field(
        default="v1", validation_alias="AGENT_TOOLS_CONTRACT_VERSION"
    )
    agent_tools_max_calls_per_turn: int = Field(
        default=5, validation_alias="AGENT_TOOLS_MAX_CALLS_PER_TURN"
    )
    agent_tools_timeout_seconds: float = Field(
        default=10.0, validation_alias="AGENT_TOOLS_TIMEOUT_SECONDS"
    )
    agent_tools_output_max_items: int = Field(
        default=20, validation_alias="AGENT_TOOLS_OUTPUT_MAX_ITEMS"
    )
    agent_proposal_ttl_hours: int = Field(
        default=24, validation_alias="AGENT_PROPOSAL_TTL_HOURS"
    )
    agent_chat_state_schema_version: int = Field(
        default=3, validation_alias="AGENT_CHAT_STATE_SCHEMA_VERSION"
    )
    agent_chat_topology_version: int = Field(
        default=3, validation_alias="AGENT_CHAT_TOPOLOGY_VERSION"
    )
    agent_intent_schema_version: str = Field(
        default="intent-v3", validation_alias="AGENT_INTENT_SCHEMA_VERSION"
    )
    agent_intent_prompt_version: str = Field(
        default="agent-intent-v1", validation_alias="AGENT_INTENT_PROMPT_VERSION"
    )
    agent_reply_prompt_version: str = Field(
        default="agent-reply-v2", validation_alias="AGENT_REPLY_PROMPT_VERSION"
    )
    agent_clarification_min_confidence: float = Field(
        default=0.6, validation_alias="AGENT_CLARIFICATION_MIN_CONFIDENCE"
    )
    agent_clarification_max_rounds: int = Field(
        default=2, validation_alias="AGENT_CLARIFICATION_MAX_ROUNDS"
    )
    agent_reply_max_refs: int = Field(
        default=10, validation_alias="AGENT_REPLY_MAX_REFS"
    )
    agent_reply_chunk_words: int = Field(
        default=8, validation_alias="AGENT_REPLY_CHUNK_WORDS"
    )
    agent_evals_dataset_version: str = Field(
        default="conversations-golden-v1",
        validation_alias="AGENT_EVALS_DATASET_VERSION",
    )
    agent_evals_releases_version: str = Field(
        default="graph-releases-v1",
        validation_alias="AGENT_EVALS_RELEASES_VERSION",
    )
    agent_evals_price_table_version: str = Field(
        default="price-table-v1",
        validation_alias="AGENT_EVALS_PRICE_TABLE_VERSION",
    )
    agent_evals_gate_enabled: bool = Field(
        default=True, validation_alias="AGENT_EVALS_GATE_ENABLED"
    )
    agent_evals_cost_threshold_pct: float = Field(
        default=20.0, validation_alias="AGENT_EVALS_COST_THRESHOLD_PCT"
    )
    agent_evals_latency_threshold_ms: int = Field(
        default=1500, validation_alias="AGENT_EVALS_LATENCY_THRESHOLD_MS"
    )
    agent_graph_release_id: str = Field(
        default="graph-release-001", validation_alias="AGENT_GRAPH_RELEASE_ID"
    )
    copilot_enabled: bool = Field(
        default=False, validation_alias="COPILOT_ENABLED"
    )
    agent_budget_window_hours: int = Field(
        default=24, validation_alias="AGENT_BUDGET_WINDOW_HOURS"
    )
    agent_budget_session_token_cap: int = Field(
        default=150000, validation_alias="AGENT_BUDGET_SESSION_TOKEN_CAP"
    )
    agent_budget_user_token_cap: int = Field(
        default=500000, validation_alias="AGENT_BUDGET_USER_TOKEN_CAP"
    )
    agent_budget_session_tool_call_cap: int = Field(
        default=40, validation_alias="AGENT_BUDGET_SESSION_TOOL_CALL_CAP"
    )
    agent_budget_user_cost_cap_usd: float = Field(
        default=5.0, validation_alias="AGENT_BUDGET_USER_COST_CAP_USD"
    )
    agent_budget_user_concurrency_cap: int = Field(
        default=2, validation_alias="AGENT_BUDGET_USER_CONCURRENCY_CAP"
    )
    agent_budget_warning_ratio: float = Field(
        default=0.8, validation_alias="AGENT_BUDGET_WARNING_RATIO"
    )
    notifications_enabled: bool = Field(
        default=True, validation_alias="NOTIFICATIONS_ENABLED"
    )
    notifications_policy_version: str = Field(
        default="notification-policy-v1",
        validation_alias="NOTIFICATIONS_POLICY_VERSION",
    )
    notifications_planner_dataset_version: str = Field(
        default="planner-golden-v1",
        validation_alias="NOTIFICATIONS_PLANNER_DATASET_VERSION",
    )
    notifications_email_from: str = Field(
        default="Umbral <alertas@umbral.local>",
        validation_alias="NOTIFICATIONS_EMAIL_FROM",
    )
    notifications_plan_job_type: str = Field(
        default="notifications.plan",
        validation_alias="NOTIFICATIONS_PLAN_JOB_TYPE",
    )
    notifications_digest_job_type: str = Field(
        default="notifications.digest",
        validation_alias="NOTIFICATIONS_DIGEST_JOB_TYPE",
    )
    notifications_deliver_job_type: str = Field(
        default="notifications.deliver",
        validation_alias="NOTIFICATIONS_DELIVER_JOB_TYPE",
    )
    notifications_unsubscribe_ttl_hours: int = Field(
        default=24, validation_alias="NOTIFICATIONS_UNSUBSCRIBE_TTL_HOURS"
    )
    notifications_default_timezone: str = Field(
        default="America/Argentina/Buenos_Aires",
        validation_alias="NOTIFICATIONS_DEFAULT_TIMEZONE",
    )

    _known_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "UMBRAL_ENV",
            "UMBRAL_RELEASE_ID",
            "UMBRAL_RELEASE_MANIFEST",
            "UMBRAL_RELEASE_DIGEST",
            "DATABASE_URL",
            "REDIS_URL",
            "OBJECT_STORE_BACKEND",
            "OBJECT_STORE_ROOT",
            "OBJECT_STORE_BUCKET",
            "OBJECT_STORE_ENDPOINT_URL",
            "OBJECT_STORE_ACCESS_KEY",
            "OBJECT_STORE_SECRET_KEY",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_HEADERS",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
            "SENTRY_DSN",
            "UMBRAL_API_BASE_URL",
            "UMBRAL_ACCESS_MODE",
            "UMBRAL_ACCESS_AUDIENCE",
            "IDENTITY_PROVIDER",
            "SUPABASE_URL",
            "SUPABASE_SECRET_KEY",
            "IDENTITY_ISSUER",
            "IDENTITY_CAPTURE_ORIGIN",
            "EMAIL_PROVIDER",
            "RESEND_API_KEY",
            "RESEND_FROM_EMAIL",
            "EMAIL_WEBHOOK_SECRET",
            "UMBRAL_BFF_TOKEN",
            "IDENTITY_FINGERPRINT_KEY",
            "SESSION_COOKIE_NAME",
            "SESSION_SECURE",
            "SILVER_GEOCODING_ENABLED",
            "SILVER_GEOCODING_ENDPOINT",
            "SILVER_GEOCODING_CACHE_SIZE",
            "SILVER_GEOCODING_RATE_LIMIT",
            "RADAR_PAGE_SIZE_DEFAULT",
            "RADAR_PAGE_SIZE_MAX",
            "RADAR_RUN_JOB_TYPE",
            "RADAR_SCORE_POLICY_VERSION",
            "RADAR_RUN_POLL_INTERVAL_SECONDS",
            "CRITERIA_SEED_VERSION",
            "CRITERIA_QUALITATIVE_MAX_ATTEMPTS",
            "CRITERIA_BATCH_SIZE",
            "CRITERIA_EXTRACTION_JOB_TYPE",
            "CRITERIA_RECOMPUTE_JOB_TYPE",
            "EXTRACTION_PROVIDER",
            "EXTRACTION_MANAGED_MODEL",
            "EXTRACTION_MANAGED_API_KEY",
            "EMBEDDINGS_ENABLED",
            "EMBEDDINGS_DIMENSION",
            "EMBEDDINGS_MODEL_VERSION_KEY",
            "URBAN_CONTEXT_ENABLED",
            "URBAN_SOURCE_LIMITS",
            "SCORING_POLICY_SEED_VERSION",
            "SCORING_LEGACY_SCORE_POLICY_VERSION",
            "SCORING_COMPARISON_MAX_LISTINGS",
            "SCORING_COMPARATOR_ENABLED",
            "SCORING_EXPLANATIONS_COPY_CONTRACT_VERSION",
            "LEARNING_POLICY_SEED_VERSION",
            "FEEDBACK_QUICK_REASONS_SEED_VERSION",
            "FEEDBACK_FREE_FEEDBACK_ENABLED",
            "FEEDBACK_MAX_FREE_FEEDBACK_LENGTH",
            "MATCHING_GOLDEN_DATASET_VERSION",
            "MATCHING_REGRESSION_GATE_ENABLED",
            "AGENT_MODEL_PROVIDER",
            "AGENT_MODEL_NAME",
            "AGENT_MODEL_TIMEOUT_SECONDS",
            "AGENT_MODEL_MAX_RETRIES",
            "AGENT_MANAGED_ENDPOINT",
            "AGENT_MANAGED_API_KEY",
            "AGENT_STATE_SCHEMA_VERSION",
            "AGENT_GRAPH_TOPOLOGY_VERSION",
            "AGENT_PROMPT_VERSION",
            "AGENT_REPLY_SCHEMA_VERSION",
            "AGENT_CHECKPOINT_RETENTION_DAYS",
            "AGENT_STRICT_MSGPACK",
            "CHAT_MESSAGE_MAX_LENGTH",
            "AGENT_TOOLS_STATE_SCHEMA_VERSION",
            "AGENT_TOOLS_TOPOLOGY_VERSION",
            "AGENT_TOOLS_CONTRACT_VERSION",
            "AGENT_TOOLS_MAX_CALLS_PER_TURN",
            "AGENT_TOOLS_TIMEOUT_SECONDS",
            "AGENT_TOOLS_OUTPUT_MAX_ITEMS",
            "AGENT_PROPOSAL_TTL_HOURS",
            "AGENT_CHAT_STATE_SCHEMA_VERSION",
            "AGENT_CHAT_TOPOLOGY_VERSION",
            "AGENT_INTENT_SCHEMA_VERSION",
            "AGENT_INTENT_PROMPT_VERSION",
            "AGENT_REPLY_PROMPT_VERSION",
            "AGENT_CLARIFICATION_MIN_CONFIDENCE",
            "AGENT_CLARIFICATION_MAX_ROUNDS",
            "AGENT_REPLY_MAX_REFS",
            "AGENT_REPLY_CHUNK_WORDS",
            "AGENT_EVALS_DATASET_VERSION",
            "AGENT_EVALS_RELEASES_VERSION",
            "AGENT_EVALS_PRICE_TABLE_VERSION",
            "AGENT_EVALS_GATE_ENABLED",
            "AGENT_EVALS_COST_THRESHOLD_PCT",
            "AGENT_EVALS_LATENCY_THRESHOLD_MS",
            "AGENT_GRAPH_RELEASE_ID",
            "AGENT_BUDGET_WINDOW_HOURS",
            "AGENT_BUDGET_SESSION_TOKEN_CAP",
            "AGENT_BUDGET_USER_TOKEN_CAP",
            "AGENT_BUDGET_SESSION_TOOL_CALL_CAP",
            "AGENT_BUDGET_USER_COST_CAP_USD",
            "AGENT_BUDGET_USER_CONCURRENCY_CAP",
            "AGENT_BUDGET_WARNING_RATIO",
            "NOTIFICATIONS_ENABLED",
            "NOTIFICATIONS_POLICY_VERSION",
            "NOTIFICATIONS_PLANNER_DATASET_VERSION",
            "NOTIFICATIONS_EMAIL_FROM",
            "NOTIFICATIONS_PLAN_JOB_TYPE",
            "NOTIFICATIONS_DIGEST_JOB_TYPE",
            "NOTIFICATIONS_DELIVER_JOB_TYPE",
            "NOTIFICATIONS_UNSUBSCRIBE_TTL_HOURS",
            "NOTIFICATIONS_DEFAULT_TIMEZONE",
        }
    )

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> Settings:
        """Validate a supplied environment without ever returning its raw values."""

        unknown = set(values) - cls._known_fields
        if unknown:
            raise SettingsValidationError("CONFIG_UNKNOWN_SETTING", sorted(unknown)[0])
        for field_name in _REQUIRED_FIELDS:
            if not values.get(field_name, "").strip():
                raise SettingsValidationError("CONFIG_REQUIRED", field_name)

        environment = values["UMBRAL_ENV"]
        if environment not in {"local", "preview", "production"}:
            raise SettingsValidationError("CONFIG_FORMAT", "UMBRAL_ENV")
        cls._validate_environment(values, environment)
        try:
            return cls.model_validate(dict(values))
        except ValueError as error:
            raise SettingsValidationError("CONFIG_FORMAT", "configuration") from error

    @classmethod
    def _validate_environment(cls, values: Mapping[str, str], environment: str) -> None:
        for field_name in ("DATABASE_URL", "REDIS_URL", "UMBRAL_API_BASE_URL"):
            cls._reject_example(value=values[field_name], field_name=field_name)

        database = _url(values["DATABASE_URL"], "DATABASE_URL")
        if database.scheme not in {"postgresql", "postgres"}:
            raise SettingsValidationError("CONFIG_FORMAT", "DATABASE_URL")
        redis = _url(values["REDIS_URL"], "REDIS_URL")
        if redis.scheme not in {"redis", "rediss"}:
            raise SettingsValidationError("CONFIG_FORMAT", "REDIS_URL")
        otel = _url(
            values["OTEL_EXPORTER_OTLP_ENDPOINT"], "OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        for field_name in (
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        ):
            if values.get(field_name, "").strip():
                signal_endpoint = _url(values[field_name], field_name)
                if environment != "local" and signal_endpoint.scheme != "https":
                    raise SettingsValidationError("CONFIG_TLS_REQUIRED", field_name)
        api = _url(values["UMBRAL_API_BASE_URL"], "UMBRAL_API_BASE_URL")

        if environment == "local":
            if (
                values["OBJECT_STORE_BACKEND"] == "filesystem"
                and not values.get("OBJECT_STORE_ROOT", "").strip()
            ):
                raise SettingsValidationError("CONFIG_REQUIRED", "OBJECT_STORE_ROOT")
            return

        for field_name, parsed in (("DATABASE_URL", database), ("REDIS_URL", redis)):
            if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                raise SettingsValidationError("CONFIG_PRIVATE_ENDPOINT", field_name)
        if values["OBJECT_STORE_BACKEND"] != "s3":
            raise SettingsValidationError("CONFIG_BACKEND", "OBJECT_STORE_BACKEND")
        railway_redis = (
            environment == "preview"
            and redis.scheme == "redis"
            and (redis.hostname or "").endswith(".railway.internal")
        )
        if redis.scheme != "rediss" and not railway_redis:
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "REDIS_URL")
        if otel.scheme != "https":
            raise SettingsValidationError(
                "CONFIG_TLS_REQUIRED", "OTEL_EXPORTER_OTLP_ENDPOINT"
            )
        railway_api = (
            environment == "preview"
            and api.scheme == "http"
            and (api.hostname or "").endswith(".railway.internal")
        )
        if (
            not railway_api
            and api.scheme == "http"
            and (api.hostname or "").endswith(".internal.invalid")
        ):
            raise SettingsValidationError(
                "CONFIG_PRIVATE_INGRESS", "UMBRAL_API_BASE_URL"
            )
        if not railway_api and api.scheme != "https":
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "UMBRAL_API_BASE_URL")
        if not railway_api and not (api.hostname or "").endswith(".internal.invalid"):
            raise SettingsValidationError(
                "CONFIG_PRIVATE_INGRESS", "UMBRAL_API_BASE_URL"
            )
        if not values.get("UMBRAL_RELEASE_DIGEST", "").strip():
            raise SettingsValidationError(
                "CONFIG_RELEASE_DIGEST_REQUIRED", "UMBRAL_RELEASE_DIGEST"
            )
        if not _DIGEST_PATTERN.fullmatch(values["UMBRAL_RELEASE_DIGEST"]):
            raise SettingsValidationError("CONFIG_FORMAT", "UMBRAL_RELEASE_DIGEST")
        for field_name in ("SENTRY_DSN",):
            if not values.get(field_name, "").strip():
                raise SettingsValidationError("CONFIG_REQUIRED", field_name)
        access_mode = values.get("UMBRAL_ACCESS_MODE", "cloudflare")
        if access_mode not in {"product_session", "cloudflare"}:
            raise SettingsValidationError("CONFIG_FORMAT", "UMBRAL_ACCESS_MODE")
        if (
            access_mode == "cloudflare"
            and not values.get("UMBRAL_ACCESS_AUDIENCE", "").strip()
        ):
            raise SettingsValidationError("CONFIG_REQUIRED", "UMBRAL_ACCESS_AUDIENCE")
        sentry = _url(values["SENTRY_DSN"], "SENTRY_DSN")
        if sentry.scheme != "https":
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "SENTRY_DSN")
        if environment == "preview":
            cls._validate_preview_providers(values)
        if (
            values.get("SESSION_COOKIE_NAME", "__Host-umbral_session")
            != "__Host-umbral_session"
        ):
            raise SettingsValidationError("CONFIG_COOKIE_NAME", "SESSION_COOKIE_NAME")
        if values.get("SESSION_SECURE", "true").lower() not in {"1", "true", "yes"}:
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "SESSION_SECURE")

    @classmethod
    def _validate_preview_providers(cls, values: Mapping[str, str]) -> None:
        if values.get("IDENTITY_PROVIDER", "fake") != "supabase":
            raise SettingsValidationError("CONFIG_PROVIDER", "IDENTITY_PROVIDER")
        if values.get("EMAIL_PROVIDER", "recording") != "resend":
            raise SettingsValidationError("CONFIG_PROVIDER", "EMAIL_PROVIDER")
        for field_name in (
            "SUPABASE_URL",
            "SUPABASE_SECRET_KEY",
            "RESEND_API_KEY",
            "RESEND_FROM_EMAIL",
            "EMAIL_WEBHOOK_SECRET",
        ):
            if not values.get(field_name, "").strip():
                raise SettingsValidationError("CONFIG_REQUIRED", field_name)
        if not values["SUPABASE_SECRET_KEY"].startswith("sb_secret_"):
            raise SettingsValidationError("CONFIG_FORMAT", "SUPABASE_SECRET_KEY")
        supabase = _url(values["SUPABASE_URL"], "SUPABASE_URL")
        if supabase.scheme != "https" or supabase.hostname != _SUPABASE_PROJECT_HOST:
            raise SettingsValidationError("CONFIG_FORMAT", "SUPABASE_URL")

    @staticmethod
    def _reject_example(value: str, field_name: str) -> None:
        parsed = urlparse(value)
        if parsed.username == "example" or parsed.password == "example":
            raise SettingsValidationError("CONFIG_EXAMPLE_VALUE", field_name)


def _url(value: str, field_name: str) -> ParseResult:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        raise SettingsValidationError("CONFIG_FORMAT", field_name)
    return parsed
