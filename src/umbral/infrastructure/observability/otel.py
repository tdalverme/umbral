"""OTel emission that treats exporter failures as degradable."""

from __future__ import annotations

from typing import Literal

from opentelemetry import metrics, trace

from umbral.application.runtime.telemetry import TelemetrySignal

DependencyName = Literal["identity_provider", "email_provider"]
DependencyState = Literal["ready", "degraded", "unavailable"]
Environment = Literal["local", "preview", "production"]
_DEPENDENCIES = frozenset({"identity_provider", "email_provider"})
_STATES = frozenset({"ready", "degraded", "unavailable"})


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
