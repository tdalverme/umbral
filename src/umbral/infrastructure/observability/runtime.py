"""Best-effort process-wide initialization for external observability."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.observability.otel import (
    ObservabilityHandle as ObservabilityHandle,
)
from umbral.infrastructure.observability.otel import initialize_otel
from umbral.infrastructure.observability.sentry import initialize_sentry

OtelInitializer = Callable[..., ObservabilityHandle | bool | None]


@dataclass(frozen=True, slots=True)
class ObservabilityDiagnostics:
    """Stable, secret-free initialization outcome for operators and tests."""

    diagnostics: tuple[str, ...]


class ObservabilityRuntime:
    """Initialize optional providers at most once for one Python process."""

    def __init__(
        self,
        *,
        initialize_otel: OtelInitializer = initialize_otel,
        initialize_sentry: Callable[..., bool] = initialize_sentry,
    ) -> None:
        self._initialize_otel = initialize_otel
        self._initialize_sentry = initialize_sentry
        self._lock = Lock()
        self._result: ObservabilityDiagnostics | None = None
        self._handle: ObservabilityHandle | None = None
        self._shutdown = False

    def initialize(self, settings: Settings) -> ObservabilityDiagnostics:
        with self._lock:
            if self._result is not None:
                return self._result
            diagnostics: list[str] = []
            try:
                otlp_result = self._initialize_otel(
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    resource_attributes=_resource_attributes(settings),
                )
            except Exception:
                otlp_result = None
            if isinstance(otlp_result, ObservabilityHandle):
                self._handle = otlp_result
            otlp_ready = bool(otlp_result)
            if not otlp_ready:
                diagnostics.append("observability.otlp_unavailable")
            try:
                sentry_ready = self._initialize_sentry(
                    settings.sentry_dsn, settings.release_id
                )
            except Exception:
                sentry_ready = False
            if not sentry_ready:
                diagnostics.append("observability.sentry_unavailable")
            self._result = ObservabilityDiagnostics(tuple(diagnostics))
            return self._result

    def force_flush(self) -> bool:
        """Flush providers once, keeping exporter errors outside product flows."""

        with self._lock:
            if self._handle is None:
                return True
            return self._handle.force_flush()

    def shutdown(self) -> bool:
        """Flush and close providers once, preserving normal process outcomes."""

        with self._lock:
            if self._shutdown:
                return True
            self._shutdown = True
            if self._handle is None:
                return True
            return self._handle.shutdown()


def _resource_attributes(settings: Settings) -> dict[str, str]:
    attributes = {
        "service.name": "umbral",
        "deployment.environment.name": settings.environment,
        "service.version": _bounded(settings.release_id),
    }
    if settings.release_digest:
        attributes["umbral.release.digest"] = _bounded(settings.release_digest)
    return attributes


def _bounded(value: str) -> str:
    if not value or len(value) > 128 or any(character.isspace() for character in value):
        return "unknown"
    return value


_runtime = ObservabilityRuntime()


def initialize_observability(settings: Settings) -> ObservabilityDiagnostics:
    """Initialize external telemetry without changing product composition results."""

    return _runtime.initialize(settings)


def force_flush_observability() -> bool:
    """Best-effort one-time flush for a process lifecycle boundary."""

    return _runtime.force_flush()


def shutdown_observability() -> bool:
    """Best-effort idempotent provider shutdown for a process lifecycle boundary."""

    return _runtime.shutdown()
