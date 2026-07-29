"""Metadata-only request -> job -> object correlation contract (T082)."""

from __future__ import annotations

from umbral.application.runtime.telemetry import (
    TelemetrySignal,
    build_correlation_trace,
)


def test_request_job_object_trace_keeps_only_shared_runtime_identity() -> None:
    signals = [
        TelemetrySignal(
            correlation_id="corr-1",
            service_name="api",
            environment="local",
            release_id="release-1",
            operation="http.request",
            state="complete",
            route_template="/ready",
        ),
        TelemetrySignal(
            correlation_id="corr-1",
            service_name="worker",
            environment="local",
            release_id="release-1",
            operation="job.reference",
            state="succeeded",
        ),
        TelemetrySignal(
            correlation_id="corr-1",
            service_name="worker",
            environment="local",
            release_id="release-1",
            operation="object.put",
            state="available",
        ),
    ]

    trace = build_correlation_trace(signals)

    assert [item["operation"] for item in trace] == [
        "http.request",
        "job.reference",
        "object.put",
    ]
    assert all("request_body" not in item for item in trace)
