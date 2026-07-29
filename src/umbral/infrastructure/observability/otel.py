"""OTel emission that treats exporter failures as degradable."""

from __future__ import annotations

from opentelemetry import trace

from umbral.application.runtime.telemetry import TelemetrySignal


def record_signal(signal: TelemetrySignal) -> None:
    try:
        trace.get_tracer("umbral").start_span(signal.operation).set_attributes(signal.attributes())
    except Exception:
        return
