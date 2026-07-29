"""Surface-specific readiness failure isolation (T083/T091)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from umbral.application.runtime.readiness import (
    DependencyCheckName,
    DependencyState,
    HeartbeatRegistry,
    ReadinessCheck,
    ReadinessProbe,
    ReadinessService,
)


def _check(
    name: DependencyCheckName,
    state: DependencyState,
    critical: bool,
) -> ReadinessCheck:
    return ReadinessCheck(
        name=name,
        state=state,
        critical=critical,
        code=None if state == "ready" else f"{name}.{state}",
    )


def test_redis_loss_isolated_between_api_and_scheduler() -> None:
    api = ReadinessService.for_surface(
        surface="api",
        release_id="release-1",
        probes=(
            ReadinessProbe(
                name="postgres",
                critical=True,
                check=lambda: _check("postgres", "ready", True),
            ),
            ReadinessProbe(
                name="redis",
                critical=False,
                check=lambda: _check("redis", "unavailable", False),
            ),
        ),
    )
    scheduler = ReadinessService.for_surface(
        surface="scheduler",
        release_id="release-1",
        probes=(
            ReadinessProbe(
                name="postgres",
                critical=True,
                check=lambda: _check("postgres", "ready", True),
            ),
            ReadinessProbe(
                name="redis",
                critical=True,
                check=lambda: _check("redis", "unavailable", True),
            ),
        ),
    )

    assert api.evaluate().state == "degraded"
    assert scheduler.evaluate().state == "not_ready"


def test_worker_heartbeat_fails_closed_after_sixty_seconds() -> None:
    registry = HeartbeatRegistry()
    now = datetime(2026, 7, 29, tzinfo=UTC)
    registry.observe("worker", observed_at=now)

    assert registry.is_fresh("worker", now=now + timedelta(seconds=59))
    assert not registry.is_fresh("worker", now=now + timedelta(seconds=61))
