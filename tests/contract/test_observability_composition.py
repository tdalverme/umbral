"""Composition contracts for optional, redacted operational telemetry."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from pytest import MonkeyPatch

from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.observability.otel import _endpoint_for, initialize_otel
from umbral.infrastructure.observability.runtime import (
    ObservabilityHandle,
    ObservabilityRuntime,
)
from umbral.infrastructure.observability.sentry import initialize_sentry


@dataclass
class _CapturedProvider:
    resource_attributes: dict[str, str]


@dataclass(frozen=True)
class _ExporterConfig:
    endpoint: str
    headers: dict[str, str]


@dataclass
class _FlushingProvider:
    force_flush_calls: int = 0
    shutdown_calls: int = 0

    def force_flush(self) -> bool:
        self.force_flush_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def _settings() -> Settings:
    return Settings.from_environment(
        {
            "UMBRAL_ENV": "preview",
            "UMBRAL_RELEASE_ID": "preview-20260801",
            "UMBRAL_RELEASE_MANIFEST": "/run/secrets/release.json",
            "UMBRAL_RELEASE_DIGEST": "sha256:" + "a" * 64,
            "DATABASE_URL": "postgresql://user:pass@db.preview.invalid/app",
            "REDIS_URL": "redis://redis.railway.internal/0",
            "OBJECT_STORE_BACKEND": "s3",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.preview.invalid",
            "OTEL_EXPORTER_OTLP_HEADERS": "authorization=CANARY_OTLP_API_KEY",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://otel.preview.invalid/custom-traces",
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "authorization=trace-key",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "https://otel.preview.invalid/custom-metrics",
            "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "authorization=metric-key",
            "SENTRY_DSN": "https://sentry.invalid/1",
            "UMBRAL_API_BASE_URL": "http://api.railway.internal:8000",
            "UMBRAL_ACCESS_MODE": "product_session",
            "IDENTITY_PROVIDER": "supabase",
            "SUPABASE_URL": "https://bpwgyvetbneghrtxcadm.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test_value",
            "IDENTITY_ISSUER": "https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
            "IDENTITY_CAPTURE_ORIGIN": "https://preview.umbral.invalid",
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_test_value",
            "RESEND_FROM_EMAIL": "Umbral <onboarding@resend.dev>",
            "EMAIL_WEBHOOK_SECRET": "whsec_test_value",
        }
    )


def test_runtime_initializes_safe_observability_once_without_affecting_product() -> (
    None
):
    captured: list[_CapturedProvider] = []
    sentry_calls: list[tuple[str | None, str]] = []

    def initialize_otel(
        *, settings: Settings, resource_attributes: dict[str, str]
    ) -> bool:
        assert (
            settings.otel_exporter_otlp_headers == "authorization=CANARY_OTLP_API_KEY"
        )
        captured.append(_CapturedProvider(resource_attributes))
        return True

    def initialize_sentry(dsn: str | None, release: str) -> bool:
        sentry_calls.append((dsn, release))
        return True

    runtime = ObservabilityRuntime(
        initialize_otel=initialize_otel,
        initialize_sentry=initialize_sentry,
    )

    first = runtime.initialize(_settings())
    second = runtime.initialize(_settings())

    assert first == second
    assert first.diagnostics == ()
    assert captured == [
        _CapturedProvider(
            {
                "service.name": "umbral",
                "deployment.environment.name": "preview",
                "service.version": "preview-20260801",
                "umbral.release.digest": "sha256:" + "a" * 64,
            }
        )
    ]
    assert sentry_calls == [("https://sentry.invalid/1", "preview-20260801")]


def test_runtime_keeps_product_composition_available_when_exporters_fail() -> None:
    runtime = ObservabilityRuntime(
        initialize_otel=lambda **_: False,
        initialize_sentry=lambda *_: False,
    )

    diagnostics = runtime.initialize(_settings())

    assert diagnostics.diagnostics == (
        "observability.otlp_unavailable",
        "observability.sentry_unavailable",
    )


def test_otel_uses_bounded_resource_and_standard_signal_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, _ExporterConfig] = {}
    resources: list[dict[str, str]] = []
    providers: list[TracerProvider | MeterProvider] = []
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "poison=outside-settings")
    settings = _settings().model_copy(
        update={
            "otel_exporter_otlp_headers": "shared=one%20two,override=generic",
            "otel_exporter_otlp_traces_endpoint": None,
            "otel_exporter_otlp_traces_headers": "override=traces",
            "otel_exporter_otlp_metrics_endpoint": None,
            "otel_exporter_otlp_metrics_headers": None,
        }
    )

    def trace_exporter(
        *, endpoint: str | None, headers: dict[str, str] | None
    ) -> OTLPSpanExporter:
        assert endpoint is not None
        assert headers is not None
        captured["trace"] = _ExporterConfig(endpoint, headers)
        return OTLPSpanExporter(endpoint=endpoint, headers=headers)

    def metric_exporter(
        *, endpoint: str | None, headers: dict[str, str] | None
    ) -> OTLPMetricExporter:
        assert endpoint is not None
        assert headers is not None
        captured["metric"] = _ExporterConfig(endpoint, headers)
        return OTLPMetricExporter(endpoint=endpoint, headers=headers)

    def tracer_provider(
        *, resource: Resource, shutdown_on_exit: bool
    ) -> TracerProvider:
        resources.append(
            {
                key: value
                for key, value in resource.attributes.items()
                if isinstance(value, str)
            }
        )
        provider = TracerProvider(resource=resource, shutdown_on_exit=shutdown_on_exit)
        providers.append(provider)
        return provider

    def meter_provider(
        *,
        resource: Resource,
        metric_readers: list[MetricReader],
        shutdown_on_exit: bool,
    ) -> MeterProvider:
        resources.append(
            {
                key: value
                for key, value in resource.attributes.items()
                if isinstance(value, str)
            }
        )
        provider = MeterProvider(
            resource=resource,
            metric_readers=metric_readers,
            shutdown_on_exit=shutdown_on_exit,
        )
        providers.append(provider)
        return provider

    handle = initialize_otel(
        settings=settings,
        resource_attributes={
            "service.name": "umbral",
            "deployment.environment.name": "preview",
            "service.version": "preview-20260801",
            "umbral.release.digest": "sha256:" + "a" * 64,
        },
        trace_exporter_factory=trace_exporter,
        metric_exporter_factory=metric_exporter,
        tracer_provider_factory=tracer_provider,
        meter_provider_factory=meter_provider,
        trace_provider_setter=lambda _: None,
        meter_provider_setter=lambda _: None,
    )
    assert handle is not None

    assert captured == {
        "trace": _ExporterConfig(
            "https://otel.preview.invalid/v1/traces",
            {"shared": "one two", "override": "traces"},
        ),
        "metric": _ExporterConfig(
            "https://otel.preview.invalid/v1/metrics",
            {"shared": "one two", "override": "generic"},
        ),
    }
    assert (
        resources
        == [
            {
                "service.name": "umbral",
                "deployment.environment.name": "preview",
                "service.version": "preview-20260801",
                "umbral.release.digest": "sha256:" + "a" * 64,
            }
        ]
        * 2
    )
    for provider in providers:
        provider.shutdown()


def test_otel_uses_signal_specific_endpoints_as_is_and_normalizes_legacy_base(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, _ExporterConfig] = {}
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "https://poison.invalid")
    settings = _settings().model_copy(
        update={
            "otel_exporter_otlp_endpoint": "https://otel.preview.invalid/v1/traces",
            "otel_exporter_otlp_headers": None,
            "otel_exporter_otlp_traces_endpoint": "https://collector.invalid/custom-traces",
            "otel_exporter_otlp_traces_headers": None,
            "otel_exporter_otlp_metrics_endpoint": "https://collector.invalid/custom-metrics",
            "otel_exporter_otlp_metrics_headers": None,
        }
    )

    def trace_exporter(
        *, endpoint: str | None, headers: dict[str, str] | None
    ) -> OTLPSpanExporter:
        assert endpoint is not None
        assert headers is not None
        captured["trace"] = _ExporterConfig(endpoint, headers)
        return OTLPSpanExporter(endpoint=endpoint, headers=headers)

    def metric_exporter(
        *, endpoint: str | None, headers: dict[str, str] | None
    ) -> OTLPMetricExporter:
        assert endpoint is not None
        assert headers is not None
        captured["metric"] = _ExporterConfig(endpoint, headers)
        return OTLPMetricExporter(endpoint=endpoint, headers=headers)

    handle = initialize_otel(
        settings=settings,
        resource_attributes={"service.name": "umbral"},
        trace_exporter_factory=trace_exporter,
        metric_exporter_factory=metric_exporter,
        trace_provider_setter=lambda _: None,
        meter_provider_setter=lambda _: None,
    )
    assert handle is not None
    handle.shutdown()

    assert captured == {
        "trace": _ExporterConfig(
            "https://collector.invalid/custom-traces",
            {},
        ),
        "metric": _ExporterConfig(
            "https://collector.invalid/custom-metrics",
            {},
        ),
    }


def test_otel_normalizes_legacy_trace_suffix_without_doubling_paths() -> None:
    assert (
        _endpoint_for("traces", "https://otel.preview.invalid/v1/traces")
        == "https://otel.preview.invalid/v1/traces"
    )
    assert (
        _endpoint_for("metrics", "https://otel.preview.invalid/v1/traces")
        == "https://otel.preview.invalid/v1/metrics"
    )


def test_malformed_otlp_headers_fail_closed_without_exposing_canary(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "CANARY_OTLP_HEADER_SECRET"
    settings = _settings().model_copy(
        update={
            "otel_exporter_otlp_headers": f"authorization={canary}%0Ainjected",
            "otel_exporter_otlp_traces_headers": None,
            "otel_exporter_otlp_metrics_headers": None,
        }
    )
    exporter_calls: list[str] = []

    result = initialize_otel(
        settings=settings,
        resource_attributes={"service.name": "umbral"},
        trace_exporter_factory=lambda **_: exporter_calls.append("traces"),
        metric_exporter_factory=lambda **_: exporter_calls.append("metrics"),
    )
    diagnostics = ObservabilityRuntime(
        initialize_otel=initialize_otel,
        initialize_sentry=lambda *_: True,
    ).initialize(settings)

    captured = capsys.readouterr()
    assert result is None
    assert exporter_calls == []
    assert diagnostics.diagnostics == ("observability.otlp_unavailable",)
    assert canary not in repr(settings) + captured.out + captured.err + caplog.text


def test_runtime_flushes_and_shuts_down_each_provider_once() -> None:
    tracer = _FlushingProvider()
    meter = _FlushingProvider()
    runtime = ObservabilityRuntime(
        initialize_otel=lambda **_: ObservabilityHandle(tracer, meter),
        initialize_sentry=lambda *_: True,
    )

    runtime.initialize(_settings())
    runtime.force_flush()
    runtime.shutdown()
    runtime.shutdown()

    assert tracer.force_flush_calls == meter.force_flush_calls == 1
    assert tracer.shutdown_calls == meter.shutdown_calls == 1


def test_runtime_shutdown_swallows_provider_failures_without_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingProvider:
        def force_flush(self) -> bool:
            raise RuntimeError("https://collector.invalid/?token=secret")

        def shutdown(self) -> None:
            raise RuntimeError("https://collector.invalid/?token=secret")

    runtime = ObservabilityRuntime(
        initialize_otel=lambda **_: ObservabilityHandle(
            FailingProvider(), FailingProvider()
        ),
        initialize_sentry=lambda *_: True,
    )

    runtime.initialize(_settings())

    assert runtime.shutdown() is False
    captured = capsys.readouterr()
    assert "collector.invalid" not in captured.out + captured.err


def test_api_lifespan_initializes_and_shuts_down_observability_once(
    monkeypatch: MonkeyPatch,
) -> None:
    import umbral.api.main as api_main

    initialized: list[Settings] = []
    shut_down: list[None] = []
    monkeypatch.setattr(api_main, "initialize_observability", initialized.append)
    monkeypatch.setattr(
        api_main,
        "shutdown_observability",
        lambda: shut_down.append(None),
        raising=False,
    )

    app = api_main.create_app()

    assert initialized == []
    with TestClient(app):
        assert len(initialized) == 1
    assert shut_down == [None]


def test_sentry_disables_default_pii_and_scrubs_transaction_events() -> None:
    captured: dict[str, object] = {}

    assert initialize_sentry(
        "https://sentry.invalid/1",
        "preview-20260801",
        initializer=lambda **kwargs: captured.update(kwargs),
    )

    filtered = captured["before_send_transaction"](  # type: ignore[operator]
        {
            "tags": {"operation": "request.completed", "email": "person@example.com"},
            "request": {"url": "https://private.invalid/?token=secret"},
            "contexts": {"body": "secret"},
        },
        {},
    )
    assert captured["send_default_pii"] is False
    assert filtered == {"tags": {"operation": "request.completed"}}
