"""OTel emission that treats exporter failures as degradable."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any, Literal

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.util.re import parse_env_headers

from umbral.application.runtime.telemetry import TelemetrySignal

DependencyName = Literal["identity_provider", "email_provider"]
DependencyState = Literal["ready", "degraded", "unavailable"]
Environment = Literal["local", "preview", "production"]
_DEPENDENCIES = frozenset({"identity_provider", "email_provider"})
_STATES = frozenset({"ready", "degraded", "unavailable"})


def initialize_otel(
    *,
    endpoint: str,
    resource_attributes: Mapping[str, str],
    trace_exporter_factory: Callable[..., Any] = OTLPSpanExporter,
    metric_exporter_factory: Callable[..., Any] = OTLPMetricExporter,
    tracer_provider_factory: Callable[..., TracerProvider] = TracerProvider,
    meter_provider_factory: Callable[..., MeterProvider] = MeterProvider,
    trace_provider_setter: Callable[[trace.TracerProvider], None] = (
        trace.set_tracer_provider
    ),
    meter_provider_setter: Callable[[metrics.MeterProvider], None] = (
        metrics.set_meter_provider
    ),
) -> bool:
    """Install bounded OTLP HTTP providers, treating configuration as optional."""

    try:
        resource = Resource(dict(resource_attributes))
        trace_exporter = trace_exporter_factory(
            endpoint=_endpoint_for("traces", endpoint),
            headers=_headers_for("TRACES"),
        )
        metric_exporter = metric_exporter_factory(
            endpoint=_endpoint_for("metrics", endpoint),
            headers=_headers_for("METRICS"),
        )
        tracer_provider = tracer_provider_factory(
            resource=resource,
            shutdown_on_exit=False,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        meter_provider = meter_provider_factory(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
            shutdown_on_exit=False,
        )
        trace_provider_setter(tracer_provider)
        meter_provider_setter(meter_provider)
    except Exception:
        return False
    return True


def _endpoint_for(signal: str, configured_endpoint: str) -> str:
    signal_endpoint = os.getenv(f"OTEL_EXPORTER_OTLP_{signal.upper()}_ENDPOINT")
    if signal_endpoint:
        return signal_endpoint
    return f"{configured_endpoint.rstrip('/')}/v1/{signal}"


def _headers_for(signal: str) -> dict[str, str]:
    generic = parse_env_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""))
    specific = parse_env_headers(
        os.getenv(f"OTEL_EXPORTER_OTLP_{signal}_HEADERS", "")
    )
    return {**generic, **specific}


def record_signal(signal: TelemetrySignal) -> None:
    try:
        trace.get_tracer("umbral").start_span(signal.operation).set_attributes(signal.attributes())
    except Exception:
        return


def dependency_metric_attributes(
    *,
    dependency: DependencyName,
    state: DependencyState,
    environment: Environment,
    release_id: str,
) -> dict[str, str]:
    """Return the bounded dimensions allowed for login dependency metrics."""

    if dependency not in _DEPENDENCIES:
        raise ValueError("dependency dimension is not allowlisted")
    if state not in _STATES:
        raise ValueError("dependency state is not allowlisted")
    if not release_id or len(release_id) > 128 or any(
        character.isspace() for character in release_id
    ):
        raise ValueError("release_id must be bounded and opaque")
    return {
        "dependency": dependency,
        "state": state,
        "environment": environment,
        "release_id": release_id,
    }


def record_dependency_metric(
    *,
    dependency: DependencyName,
    state: DependencyState,
    environment: Environment,
    release_id: str,
) -> None:
    """Emit one bounded metric and swallow exporter failures safely."""

    attributes = dependency_metric_attributes(
        dependency=dependency,
        state=state,
        environment=environment,
        release_id=release_id,
    )
    try:
        metrics.get_meter("umbral").create_counter(
            "umbral_identity_dependency_events",
            unit="1",
        ).add(1, attributes)
    except Exception:
        return
