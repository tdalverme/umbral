"""Pure readiness aggregation behavior."""

from __future__ import annotations

from umbral.application.runtime.readiness import (
    ReadinessCheck,
    ReadinessModule,
)


def test_readiness_marks_critical_unavailable_check_as_not_ready() -> None:
    module = ReadinessModule(
        surface="api",
        release_id="foundation-local",
        probes=(
            lambda: ReadinessCheck(
                name="postgres", state="unavailable", critical=True, code="db.down"
            ),
            lambda: ReadinessCheck(name="redis", state="ready", critical=False),
        ),
    )

    report = module.evaluate()

    assert report.surface == "api"
    assert report.state == "not_ready"
    assert report.release_id == "foundation-local"
    assert report.checks == (
        ReadinessCheck(
            name="postgres", state="unavailable", critical=True, code="db.down"
        ),
        ReadinessCheck(name="redis", state="ready", critical=False),
    )


def test_readiness_marks_noncritical_degradation_without_withdrawing_surface() -> None:
    module = ReadinessModule(
        surface="api",
        release_id="foundation-local",
        probes=(
            lambda: ReadinessCheck(name="runtime_config", state="ready", critical=True),
            lambda: ReadinessCheck(
                name="telemetry", state="degraded", critical=False, code="otel.slow"
            ),
        ),
    )

    assert module.evaluate().state == "degraded"
