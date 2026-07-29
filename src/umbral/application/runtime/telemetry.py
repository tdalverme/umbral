"""Typed, metadata-only signals shared by runtime adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ServiceName = Literal["web", "api", "worker", "scheduler"]


@dataclass(frozen=True, slots=True)
class TelemetrySignal:
    correlation_id: str
    service_name: ServiceName
    environment: Literal["local", "preview", "production"]
    release_id: str
    operation: str
    state: str
    request_id: str | None = None
    status_code: int | None = None
    duration_ms: int | None = None
    route_template: str | None = None
    http_method: str | None = None
    error_code: str | None = None

    def attributes(self) -> dict[str, str | int]:
        """Return only declared, non-null signal metadata."""
        return {key: value for key, value in asdict(self).items() if value is not None}
