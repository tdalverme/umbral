"""Side-effect-free readiness aggregation for a single runtime surface."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

Surface = Literal["web", "api", "worker", "scheduler"]
ReadinessState = Literal["ready", "degraded", "not_ready"]
DependencyState = Literal["ready", "degraded", "unavailable"]
DependencyCheckName = Literal[
    "runtime_config",
    "api",
    "postgres",
    "schema",
    "postgis",
    "pgvector",
    "redis",
    "object_storage",
    "execution_loop",
    "scheduling_loop",
    "telemetry",
]
_ALLOWED_CHECK_NAMES = frozenset(
    {
        "runtime_config",
        "api",
        "postgres",
        "schema",
        "postgis",
        "pgvector",
        "redis",
        "object_storage",
        "execution_loop",
        "scheduling_loop",
        "telemetry",
    }
)
_ALLOWED_CHECK_CODES = frozenset(
    {
        "runtime_config.degraded",
        "runtime_config.unavailable",
        "api.degraded",
        "api.unavailable",
        "postgres.degraded",
        "postgres.unavailable",
        "schema.degraded",
        "schema.unavailable",
        "postgis.degraded",
        "postgis.unavailable",
        "pgvector.degraded",
        "pgvector.unavailable",
        "redis.degraded",
        "redis.unavailable",
        "object_storage.degraded",
        "object_storage.unavailable",
        "execution_loop.degraded",
        "execution_loop.unavailable",
        "scheduling_loop.degraded",
        "scheduling_loop.unavailable",
        "telemetry.degraded",
        "telemetry.unavailable",
    }
)


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """One already-observed, allowlisted dependency condition."""

    name: DependencyCheckName
    state: DependencyState
    critical: bool
    code: str | None = None

    def __post_init__(self) -> None:
        if self.name not in _ALLOWED_CHECK_NAMES:
            raise ValueError("readiness check name is not allowlisted")
        if self.code is not None and self.code not in _ALLOWED_CHECK_CODES:
            raise ValueError("readiness check code is not allowlisted")


@dataclass(frozen=True, slots=True)
class ReadinessProbe:
    """Metadata required to represent a failed probe safely."""

    name: DependencyCheckName
    critical: bool
    check: Callable[[], ReadinessCheck]

    def __post_init__(self) -> None:
        if self.name not in _ALLOWED_CHECK_NAMES:
            raise ValueError("readiness probe name is not allowlisted")


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """An immutable readiness result with no persistence side effects."""

    surface: Surface
    state: ReadinessState
    observed_at: datetime
    release_id: str
    checks: tuple[ReadinessCheck, ...]


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

        checks = tuple(self._evaluate_probe(probe) for probe in self._probes)
        state = _aggregate_state(checks)
        return ReadinessReport(
            surface=self._surface,
            state=state,
            observed_at=datetime.now(UTC),
            release_id=self._release_id,
            checks=checks,
        )

    @staticmethod
    def _evaluate_probe(probe: ReadinessProbe) -> ReadinessCheck:
        try:
            check = probe.check()
        except Exception:
            return _unavailable_check(probe)
        if (
            not isinstance(check, ReadinessCheck)
            or check.name != probe.name
            or check.critical != probe.critical
        ):
            return _unavailable_check(probe)
        return check


class ReadinessService:
    """Compose isolated, side-effect-free readiness modules by surface."""

    @staticmethod
    def for_surface(
        *,
        surface: Surface,
        release_id: str,
        probes: tuple[ReadinessProbe, ...],
    ) -> ReadinessModule:
        return ReadinessModule(
            surface=surface,
            release_id=release_id,
            probes=probes,
        )


@dataclass(frozen=True, slots=True)
class Heartbeat:
    surface: Surface
    observed_at: datetime


class HeartbeatRegistry:
    """In-memory heartbeat view; stale worker/scheduler entries fail closed."""

    def __init__(self, *, stale_after_seconds: int = 60) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._heartbeats: dict[Surface, Heartbeat] = {}

    def observe(self, surface: Surface, *, observed_at: datetime) -> None:
        self._heartbeats[surface] = Heartbeat(surface, observed_at)

    def is_fresh(self, surface: Surface, *, now: datetime) -> bool:
        heartbeat = self._heartbeats.get(surface)
        if heartbeat is None:
            return False
        return (
            now.astimezone(UTC) - heartbeat.observed_at.astimezone(UTC)
        ).total_seconds() <= self._stale_after_seconds

def _aggregate_state(checks: tuple[ReadinessCheck, ...]) -> ReadinessState:
    if any(check.critical and check.state != "ready" for check in checks):
        return "not_ready"
    if any(check.state != "ready" for check in checks):
        return "degraded"
    return "ready"


def _unavailable_check(probe: ReadinessProbe) -> ReadinessCheck:
    return ReadinessCheck(
        name=probe.name,
        state="unavailable",
        critical=probe.critical,
        code=f"{probe.name}.unavailable",
    )
