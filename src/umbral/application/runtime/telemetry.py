"""Typed, metadata-only signals shared by runtime adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

ServiceName = Literal["web", "api", "worker", "scheduler"]
Environment = Literal["local", "preview", "production"]


@dataclass(frozen=True, slots=True)
class TelemetrySignal:
    correlation_id: str
    service_name: ServiceName
    environment: Environment
    release_id: str
    operation: str
    state: str
    request_id: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    route_template: str | None = None
    http_method: str | None = None
    error_code: str | None = None
    job_type: str | None = None
    job_state: str | None = None
    attempt_number: int | None = None
    queue_lag_ms: int | None = None
    object_operation: str | None = None
    content_class: str | None = None

    def attributes(self) -> dict[str, str | int]:
        """Return only declared, non-null signal metadata."""
        return {key: value for key, value in asdict(self).items() if value is not None}


def build_correlation_trace(
    signals: Iterable[TelemetrySignal],
) -> tuple[dict[str, str | int], ...]:
    """Return a metadata-only request/job/object trace with one identity."""

    ordered = tuple(signals)
    if not ordered:
        raise ValueError("a correlation trace requires at least one signal")
    correlation_id = ordered[0].correlation_id
    release_id = ordered[0].release_id
    if any(
        signal.correlation_id != correlation_id or signal.release_id != release_id
        for signal in ordered
    ):
        raise ValueError("correlation trace identity must be stable")
    return tuple(signal.attributes() for signal in ordered)
