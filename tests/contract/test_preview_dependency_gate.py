"""Contract for the preview managed-dependency conformance gate."""

from __future__ import annotations

from pathlib import Path


class _Clients:
    def __init__(self) -> None:
        self.redis_messages: list[bytes] = []
        self.objects: dict[tuple[str, str], bytes] = {}
        self.http_requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def postgres(self, operation: str) -> object:
        values: dict[str, object] = {
            "server_major": 17,
            "alembic_revision": "0001_foundation_runtime",
            "extensions": {"postgis", "vector"},
        }
        return values[operation]

    def redis(self, operation: str, value: bytes | None = None) -> object:
        if operation == "ping":
            return "PONG"
        if operation == "enqueue":
            assert value is not None
            self.redis_messages.append(value)
            return "queued"
        if operation == "dequeue":
            return self.redis_messages.pop(0)
        raise AssertionError(operation)

    def object_store(
        self, operation: str, bucket: str, key: str, body: bytes | None = None
    ) -> object:
        if operation == "put":
            assert body is not None
            self.objects[(bucket, key)] = body
            return {"size_bytes": len(body)}
        if operation == "stat":
            return {"size_bytes": len(self.objects[(bucket, key)])}
        if operation == "get":
            return self.objects[(bucket, key)]
        if operation == "copy":
            assert body is not None
            source_bucket, source_key = body.decode().split("/", maxsplit=1)
            self.objects[(bucket, key)] = self.objects[(source_bucket, source_key)]
            return {"size_bytes": len(self.objects[(bucket, key)])}
        raise AssertionError(operation)

    def http(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> object:
        self.http_requests.append((method, url, headers, body))
        if "sentry" in url:
            return {"status_code": 202, "event_id": "evt-preview-probe"}
        return 200


def _config() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql://runtime:runtime@ep-preview-pooler.neon.tech/umbral",
        "DATABASE_MIGRATION_URL": "postgresql://migration:migration@ep-preview.neon.tech/umbral",
        "OBJECT_STORE_BUCKET": "umbral-primary",
        "R2_RECOVERY_BUCKET": "umbral-recovery",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.test",
        "SENTRY_DSN": "https://sentry-secret@sentry.example.test/42",
        "SUPABASE_URL": "https://configured-project.supabase.co",
        "IDENTITY_ISSUER": "https://configured-project.supabase.co/auth/v1",
        "SUPABASE_SECRET_KEY": "sb_secret_test_value",
        "RESEND_API_KEY": "re_test_value",
    }


def test_preview_dependency_gate_runs_all_remote_checks_without_secret_evidence(
) -> None:
    from umbral.ops.provider_conformance import (
        PreviewDependencyClients,
        run_preview_dependency_conformance,
    )

    clients = _Clients()
    report = run_preview_dependency_conformance(
        config=_config(),
        manifest_revision="0001_foundation_runtime",
        clients=PreviewDependencyClients(
            postgres=clients.postgres,
            redis=clients.redis,
            object_store=clients.object_store,
            http=clients.http,
        ),
    )

    assert report.passed
    assert {check.name for check in report.checks} == {
        "postgres.server_major",
        "postgres.alembic_revision",
        "postgres.extensions",
        "database.url_roles",
        "redis.round_trip",
        "r2.primary_round_trip",
        "r2.recovery_copy",
        "grafana.otlp",
        "sentry.event",
        "supabase.issuer",
        "supabase.reachability",
        "resend.reachability",
    }
    evidence = report.to_dict()
    assert evidence["passed"] is True
    assert "runtime" not in repr(evidence)
    assert "sentry-secret" not in repr(evidence)
    assert "re_test_value" not in repr(evidence)
    assert {request[1] for request in clients.http_requests} == {
        "https://otel.example.test/v1/traces",
        "https://sentry.example.test/api/42/store/",
        "https://configured-project.supabase.co/auth/v1/health",
        "https://api.resend.com/domains",
    }
    sentry_request = next(
        request for request in clients.http_requests if "sentry" in request[1]
    )
    sentry_check = next(
        check for check in report.checks if check.name == "sentry.event"
    )
    assert sentry_check.evidence == {"event_id": "evt-preview-probe"}
    assert sentry_request[3] is not None
    assert b"sentry-secret" not in sentry_request[3]


def test_preview_dependency_gate_rejects_a_direct_runtime_database_url() -> None:
    from umbral.ops.provider_conformance import (
        PreviewDependencyClients,
        run_preview_dependency_conformance,
    )

    config = _config()
    config["DATABASE_URL"] = config["DATABASE_MIGRATION_URL"]
    clients = _Clients()

    report = run_preview_dependency_conformance(
        config=config,
        manifest_revision="0001_foundation_runtime",
        clients=PreviewDependencyClients(
            postgres=clients.postgres,
            redis=clients.redis,
            object_store=clients.object_store,
            http=clients.http,
        ),
    )

    assert not report.passed
    assert next(
        check for check in report.checks if check.name == "database.url_roles"
    ).code == "dependency.failed"


def test_promotion_workflow_orders_dependency_gates_before_exact_image_switch() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "promote.yml"
    ).read_text(encoding="utf-8")

    ordered_commands = (
        "verify-access.ps1",
        "validate-railway-config.ps1",
        "backup-preview.ps1",
        "migrate-preview.ps1",
        "check-preview-dependencies.ps1",
        "set-railway-images.ps1",
        "smoke.ps1",
    )
    positions = [workflow.index(command) for command in ordered_commands]

    assert positions == sorted(positions)
