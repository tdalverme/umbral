"""Closed-field contracts for operational signals."""

from __future__ import annotations

import json
from io import StringIO

from umbral.application.runtime.telemetry import TelemetrySignal
from umbral.infrastructure.observability.filtering import filter_sentry_event
from umbral.infrastructure.observability.logging import JsonTelemetryLogger


def _contains(value: object, needle: str) -> bool:
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return value == needle


def test_json_logging_emits_only_closed_metadata_fields() -> None:
    stream = StringIO()
    signal = TelemetrySignal(
        correlation_id="1d0e27a2-4bc9-48b0-bc5f-c33df906a990",
        service_name="api",
        environment="local",
        release_id="foundation-local",
        operation="request.completed",
        state="success",
        route_template="/listings/{listing_id}",
        http_method="GET",
        duration_ms=12,
    )

    JsonTelemetryLogger(stream).emit(signal)

    payload = json.loads(stream.getvalue())
    assert payload == {
        "correlation_id": "1d0e27a2-4bc9-48b0-bc5f-c33df906a990",
        "service_name": "api",
        "environment": "local",
        "release_id": "foundation-local",
        "operation": "request.completed",
        "state": "success",
        "route_template": "/listings/{listing_id}",
        "http_method": "GET",
        "duration_ms": 12,
    }


def test_sentry_filter_recursively_drops_canaries_and_unknown_fields() -> None:
    canary = "CANARY_SECRET_DO_NOT_EXPORT"
    event = {
        "tags": {"operation": "request.completed", "unknown": canary},
        "request": {"url": f"https://private.invalid/?token={canary}"},
        "exception": {"values": [{"value": canary}]},
        "extra": {"body": canary},
    }

    filtered = filter_sentry_event(event)

    assert filtered == {"tags": {"operation": "request.completed"}}
    assert not _contains(filtered, canary)
