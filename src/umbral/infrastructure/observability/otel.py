"""OTel emission that treats exporter failures as degradable."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from threading import RLock
from typing import Any, Literal
from urllib.parse import unquote

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from umbral.application.runtime.telemetry import TelemetrySignal
from umbral.infrastructure.config.settings import Settings

DependencyName = Literal["identity_provider", "email_provider"]
DependencyState = Literal["ready", "degraded", "unavailable"]
Environment = Literal["local", "preview", "production"]
_DEPENDENCIES = frozenset({"identity_provider", "email_provider"})
_STATES = frozenset({"ready", "degraded", "unavailable"})
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_HEX = frozenset("0123456789abcdefABCDEF")


class ObservabilityHandle:
    """One safely closable pair of globally registered OTel providers."""

    def __init__(self, tracer_provider: object, meter_provider: object) -> None:
        self._providers = (tracer_provider, meter_provider)
        self._lock = RLock()
        self._flushed = False
        self._shutdown = False

    def force_flush(self) -> bool:
        with self._lock:
            if self._flushed or self._shutdown:
                return True
            self._flushed = True
            return _call_providers(self._providers, "force_flush")

    def shutdown(self) -> bool:
        with self._lock:
            if self._shutdown:
                return True
            self.force_flush()
            self._shutdown = True
            return _call_providers(self._providers, "shutdown")


def initialize_otel(
    *,
    settings: Settings,
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
) -> ObservabilityHandle | None:
    """Install bounded OTLP HTTP providers, treating configuration as optional."""

    try:
        resource = Resource(dict(resource_attributes))
        trace_exporter = trace_exporter_factory(
            endpoint=_endpoint_for(
                "traces",
                settings.otel_exporter_otlp_endpoint,
                settings.otel_exporter_otlp_traces_endpoint,
            ),
            headers=_headers_for(
                settings.otel_exporter_otlp_headers,
                settings.otel_exporter_otlp_traces_headers,
            ),
        )
        metric_exporter = metric_exporter_factory(
            endpoint=_endpoint_for(
                "metrics",
                settings.otel_exporter_otlp_endpoint,
                settings.otel_exporter_otlp_metrics_endpoint,
            ),
            headers=_headers_for(
                settings.otel_exporter_otlp_headers,
                settings.otel_exporter_otlp_metrics_headers,
            ),
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
        return None
    return ObservabilityHandle(tracer_provider, meter_provider)


def _endpoint_for(
    signal: str,
    configured_endpoint: str,
    signal_endpoint: str | None = None,
) -> str:
    if signal_endpoint:
        return signal_endpoint
    return f"{_generic_endpoint_base(configured_endpoint)}/v1/{signal}"


def _generic_endpoint_base(configured_endpoint: str) -> str:
    endpoint = configured_endpoint.rstrip("/")
    for signal in ("traces", "metrics", "logs"):
        suffix = f"/v1/{signal}"
        if endpoint.endswith(suffix):
            return endpoint.removesuffix(suffix)
    return endpoint


def _headers_for(
    generic_headers: str | None,
    signal_headers: str | None,
) -> dict[str, str]:
    generic = _parse_headers(generic_headers)
    specific = _parse_headers(signal_headers)
    return {**generic, **specific}


def _parse_headers(value: str | None) -> dict[str, str]:
    """Parse standard OTLP comma-separated headers without provider logging."""

    if value is None or not value.strip():
        return {}
    headers: dict[str, str] = {}
    for raw_entry in value.split(","):
        entry = raw_entry.strip()
        if not entry or "=" not in entry:
            raise ValueError("OTLP_HEADERS_INVALID")
        raw_name, raw_value = entry.split("=", 1)
        name = _decode_header_component(raw_name.strip())
        header_value = _decode_header_component(raw_value.strip())
        if not _HEADER_NAME.fullmatch(name) or _contains_control(header_value):
            raise ValueError("OTLP_HEADERS_INVALID")
        headers[name] = header_value
    return headers


def _decode_header_component(value: str) -> str:
    for index, character in enumerate(value):
        if character == "%" and (
            index + 2 >= len(value)
            or value[index + 1] not in _HEX
            or value[index + 2] not in _HEX
        ):
            raise ValueError("OTLP_HEADERS_INVALID")
    decoded = unquote(value)
    if _contains_control(decoded):
        raise ValueError("OTLP_HEADERS_INVALID")
    return decoded


def _contains_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _call_providers(providers: tuple[object, object], method_name: str) -> bool:
    successful = True
    for provider in providers:
        method = getattr(provider, method_name, None)
        if not callable(method):
            successful = False
            continue
        try:
            if method() is False:
                successful = False
        except Exception:
            successful = False
    return successful


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
