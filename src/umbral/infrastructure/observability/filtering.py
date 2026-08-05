"""Defensive filtering for provider payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_ALLOWED = frozenset({
    "correlation_id", "request_id", "service_name", "environment", "release_id",
    "operation", "state", "status_code", "duration_ms", "route_template",
    "http_method", "error_code", "job_type", "job_state", "attempt_number",
    "queue_lag_ms", "object_operation", "content_class",
})


def filter_attributes(attributes: Mapping[str, object]) -> dict[str, str | int]:
    return {
        key: value
        for key, value in attributes.items()
        if key in _ALLOWED
        and isinstance(value, (str, int))
        and not isinstance(value, bool)
    }


def filter_sentry_event(
    event: Mapping[str, Any], hint: object | None = None
) -> dict[str, object] | None:
    """Keep provider events metadata-only; never preserve exception/request data."""
    tags = event.get("tags")
    safe_tags = filter_attributes(tags) if isinstance(tags, Mapping) else {}
    return {"tags": safe_tags} if safe_tags else None


_SENSITIVE_NAMES = frozenset({
    "email", "normalized_email", "token", "token_hash", "cookie", "session_token",
    "authorization", "raw_body", "body", "secret", "url", "query", "recipient",
    "subject", "message", "password",
})


def redact_identity_payload(value: object) -> object:
    """Recursively drop identity bearer material and unnecessary PII."""

    if isinstance(value, Mapping):
        return {
            str(key): redact_identity_payload(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_NAMES
        }
    if isinstance(value, list):
        return [redact_identity_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_identity_payload(item) for item in value)
    return value
