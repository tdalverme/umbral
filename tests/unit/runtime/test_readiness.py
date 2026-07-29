"""Pure readiness aggregation behavior."""

from __future__ import annotations

from typing import cast

import pytest

from umbral.application.runtime.readiness import (
    DependencyCheckName,
    ReadinessCheck,
    ReadinessModule,
    ReadinessProbe,
)


def test_readiness_marks_critical_unavailable_check_as_not_ready() -> None:
    module = ReadinessModule(
        surface="api",
        release_id="foundation-local",
        probes=(
            ReadinessProbe(
                name="postgres",
                critical=True,
                check=lambda: ReadinessCheck(
                    name="postgres",
                    state="unavailable",
                    critical=True,
                    code="postgres.unavailable",
                ),
            ),
            ReadinessProbe(
                name="redis",
                critical=False,
                check=lambda: ReadinessCheck(
                    name="redis", state="ready", critical=False
                ),
            ),
        ),
    )

    report = module.evaluate()

    assert report.surface == "api"
    assert report.state == "not_ready"
    assert report.release_id == "foundation-local"
    assert report.checks == (
        ReadinessCheck(
            name="postgres",
            state="unavailable",
            critical=True,
            code="postgres.unavailable",
        ),
        ReadinessCheck(name="redis", state="ready", critical=False),
    )


def test_readiness_marks_noncritical_degradation_without_withdrawing_surface() -> None:
    module = ReadinessModule(
        surface="api",
        release_id="foundation-local",
        probes=(
            ReadinessProbe(
                name="runtime_config",
                critical=True,
                check=lambda: ReadinessCheck(
                    name="runtime_config", state="ready", critical=True
                ),
            ),
            ReadinessProbe(
                name="telemetry",
                critical=False,
                check=lambda: ReadinessCheck(
                    name="telemetry",
                    state="degraded",
                    critical=False,
                    code="telemetry.degraded",
                ),
            ),
        ),
    )

    assert module.evaluate().state == "degraded"


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("arbitrary_dependency", None),
        ("postgres", "db.down"),
    ],
)
def test_readiness_check_rejects_names_and_codes_outside_contract_allowlists(
    name: str, code: str | None
) -> None:
    with pytest.raises(ValueError):
        ReadinessCheck(
            name=cast(DependencyCheckName, name),
            state="unavailable",
            critical=True,
            code=code,
        )


def test_readiness_converts_a_probe_exception_to_safe_unavailable_check() -> None:
    def failing_probe() -> ReadinessCheck:
        raise RuntimeError("SECRET_PROBE_FAILURE")

    module = ReadinessModule(
        surface="api",
        release_id="foundation-local",
        probes=(
            ReadinessProbe(name="postgres", critical=True, check=failing_probe),
        ),
    )

    report = module.evaluate()

    assert report.state == "not_ready"
    assert report.checks == (
        ReadinessCheck(
            name="postgres",
            state="unavailable",
            critical=True,
            code="postgres.unavailable",
        ),
    )
    assert "SECRET_PROBE_FAILURE" not in repr(report)


def test_readiness_converts_malformed_probe_result_to_safe_unavailable_check() -> None:
    def malformed_probe() -> ReadinessCheck:
        return object()  # type: ignore[return-value]

    module = ReadinessModule(
        surface="api",
        release_id="foundation-local",
        probes=(
            ReadinessProbe(name="postgres", critical=True, check=malformed_probe),
        ),
    )

    assert module.evaluate().checks == (
        ReadinessCheck(
            name="postgres",
            state="unavailable",
            critical=True,
            code="postgres.unavailable",
        ),
    )
