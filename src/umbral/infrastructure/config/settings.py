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
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    api_base_url: str = Field(validation_alias="UMBRAL_API_BASE_URL")
    access_audience: str | None = Field(
        default=None, validation_alias="UMBRAL_ACCESS_AUDIENCE"
    )
    identity_provider: str = Field(default="fake", validation_alias="IDENTITY_PROVIDER")
    identity_issuer: str = Field(default="fake://local", validation_alias="IDENTITY_ISSUER")
    identity_capture_origin: str = Field(default="http://localhost:3000", validation_alias="IDENTITY_CAPTURE_ORIGIN")
    email_provider: str = Field(default="recording", validation_alias="EMAIL_PROVIDER")
    resend_api_key: str | None = Field(default=None, validation_alias="RESEND_API_KEY")
    email_webhook_secret: str | None = Field(default=None, validation_alias="EMAIL_WEBHOOK_SECRET")
    bff_token: str = Field(default="local-bff-token", validation_alias="UMBRAL_BFF_TOKEN")
    identity_fingerprint_key: str = Field(default="local-identity-fingerprint-key", validation_alias="IDENTITY_FINGERPRINT_KEY")
    session_cookie_name: str = Field(default="__Host-umbral_session", validation_alias="SESSION_COOKIE_NAME")
    session_secure: bool = Field(default=True, validation_alias="SESSION_SECURE")

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
            "SENTRY_DSN",
            "UMBRAL_API_BASE_URL",
            "UMBRAL_ACCESS_AUDIENCE",
            "IDENTITY_PROVIDER",
            "IDENTITY_ISSUER",
            "IDENTITY_CAPTURE_ORIGIN",
            "EMAIL_PROVIDER",
            "RESEND_API_KEY",
            "EMAIL_WEBHOOK_SECRET",
            "UMBRAL_BFF_TOKEN",
            "IDENTITY_FINGERPRINT_KEY",
            "SESSION_COOKIE_NAME",
            "SESSION_SECURE",
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
    def _validate_environment(
        cls, values: Mapping[str, str], environment: str
    ) -> None:
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
        api = _url(values["UMBRAL_API_BASE_URL"], "UMBRAL_API_BASE_URL")

        if environment == "local":
            if values["OBJECT_STORE_BACKEND"] == "filesystem" and not values.get(
                "OBJECT_STORE_ROOT", ""
            ).strip():
                raise SettingsValidationError("CONFIG_REQUIRED", "OBJECT_STORE_ROOT")
            return

        for field_name, parsed in (("DATABASE_URL", database), ("REDIS_URL", redis)):
            if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                raise SettingsValidationError("CONFIG_PRIVATE_ENDPOINT", field_name)
        if values["OBJECT_STORE_BACKEND"] != "s3":
            raise SettingsValidationError("CONFIG_BACKEND", "OBJECT_STORE_BACKEND")
        if redis.scheme != "rediss":
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "REDIS_URL")
        if otel.scheme != "https":
            raise SettingsValidationError(
                "CONFIG_TLS_REQUIRED", "OTEL_EXPORTER_OTLP_ENDPOINT"
            )
        if api.scheme != "https" or not (api.hostname or "").endswith(
            ".internal.invalid"
        ):
            raise SettingsValidationError(
                "CONFIG_PRIVATE_INGRESS", "UMBRAL_API_BASE_URL"
            )
        if not values.get("UMBRAL_RELEASE_DIGEST", "").strip():
            raise SettingsValidationError(
                "CONFIG_RELEASE_DIGEST_REQUIRED", "UMBRAL_RELEASE_DIGEST"
            )
        if not _DIGEST_PATTERN.fullmatch(values["UMBRAL_RELEASE_DIGEST"]):
            raise SettingsValidationError("CONFIG_FORMAT", "UMBRAL_RELEASE_DIGEST")
        for field_name in ("SENTRY_DSN", "UMBRAL_ACCESS_AUDIENCE"):
            if not values.get(field_name, "").strip():
                raise SettingsValidationError("CONFIG_REQUIRED", field_name)
        sentry = _url(values["SENTRY_DSN"], "SENTRY_DSN")
        if sentry.scheme != "https":
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "SENTRY_DSN")
        if "SESSION_COOKIE_NAME" in values and values["SESSION_COOKIE_NAME"] != "__Host-umbral_session":
            raise SettingsValidationError("CONFIG_COOKIE_NAME", "SESSION_COOKIE_NAME")
        if "SESSION_SECURE" in values and values["SESSION_SECURE"].lower() not in {"1", "true", "yes"}:
            raise SettingsValidationError("CONFIG_TLS_REQUIRED", "SESSION_SECURE")

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
