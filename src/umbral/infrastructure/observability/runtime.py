"""Best-effort process-wide initialization for external observability."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.observability.otel import initialize_otel
from umbral.infrastructure.observability.sentry import initialize_sentry


@dataclass(frozen=True, slots=True)
class ObservabilityDiagnostics:
    """Stable, secret-free initialization outcome for operators and tests."""

    diagnostics: tuple[str, ...]


class ObservabilityRuntime:
    """Initialize optional providers at most once for one Python process."""

    def __init__(
        self,
        *,
        initialize_otel: Callable[..., bool] = initialize_otel,
        initialize_sentry: Callable[..., bool] = initialize_sentry,
    ) -> None:
        self._initialize_otel = initialize_otel
        self._initialize_sentry = initialize_sentry
        self._lock = Lock()
        self._result: ObservabilityDiagnostics | None = None

    def initialize(self, settings: Settings) -> ObservabilityDiagnostics:
        with self._lock:
            if self._result is not None:
                return self._result
            diagnostics: list[str] = []
            try:
                otlp_ready = self._initialize_otel(
                    endpoint=settings.otel_exporter_otlp_endpoint,
                    resource_attributes=_resource_attributes(settings),
                )
            except Exception:
                otlp_ready = False
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
