"""Side-effect-free readiness aggregation for a single runtime surface."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Surface = Literal["web", "api", "worker", "scheduler"]
ReadinessState = Literal["ready", "degraded", "not_ready"]
DependencyState = Literal["ready", "degraded", "unavailable"]


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """One already-observed, allowlisted dependency condition."""

    name: str
    state: DependencyState
    critical: bool
    code: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """An immutable readiness result with no persistence side effects."""

    surface: Surface
    state: ReadinessState
    observed_at: datetime
    release_id: str
    checks: tuple[ReadinessCheck, ...]


ReadinessProbe = Callable[[], ReadinessCheck]


class ReadinessModule:
    """Evaluate supplied in-memory probes without writing or connecting."""

    def __init__(
        self,
        *,
        surface: Surface,
        release_id: str,
        probes: tuple[ReadinessProbe, ...],
    ) -> None:
        self._surface = surface
        self._release_id = release_id
        self._probes = probes

    def evaluate(self) -> ReadinessReport:
        """Aggregate the current probe values without retaining their result."""

        checks = tuple(probe() for probe in self._probes)
        state = _aggregate_state(checks)
        return ReadinessReport(
            surface=self._surface,
            state=state,
            observed_at=datetime.now(UTC),
            release_id=self._release_id,
            checks=checks,
        )


def _aggregate_state(checks: tuple[ReadinessCheck, ...]) -> ReadinessState:
    if any(check.critical and check.state != "ready" for check in checks):
        return "not_ready"
    if any(check.state != "ready" for check in checks):
        return "degraded"
    return "ready"
