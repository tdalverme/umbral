from __future__ import annotations

from umbral.application.runtime.readiness import (
    ReadinessCheck,
    ReadinessService,
    login_dependency_probes,
)
from umbral.infrastructure.observability.otel import dependency_metric_attributes


def test_identity_email_outage_degrades_login_without_withdrawing_api_readiness(
) -> None:
    module = ReadinessService.for_surface(
        surface="api",
        release_id="release-1",
        probes=login_dependency_probes(
            identity=lambda: ReadinessCheck(
                name="identity_provider",
                state="unavailable",
                critical=False,
                code="identity_provider.unavailable",
            ),
            email=lambda: ReadinessCheck(
                name="email_provider",
                state="ready",
                critical=False,
            ),
        ),
    )

    report = module.evaluate()

    assert report.state == "degraded"
    assert {check.name for check in report.checks} == {
        "identity_provider",
        "email_provider",
    }
    assert all(not check.critical for check in report.checks)


def test_dependency_metric_dimensions_are_bounded_and_non_sensitive() -> None:
    attributes = dependency_metric_attributes(
        dependency="identity_provider",
        state="degraded",
        environment="preview",
        release_id="release-1",
    )

    assert attributes == {
        "dependency": "identity_provider",
        "state": "degraded",
        "environment": "preview",
        "release_id": "release-1",
    }
    assert not any(
        forbidden in attributes
        for forbidden in ("email", "token", "origin", "url", "credential")
    )
