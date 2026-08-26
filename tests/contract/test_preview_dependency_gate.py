"""Contract for the preview managed-dependency conformance gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


class _Clients:
    def __init__(self, failure: str | None = None) -> None:
        self.failure = failure
        self.redis_messages: list[bytes] = []
        self.objects: dict[tuple[str, str], bytes] = {}
        self.http_requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def postgres(self, operation: str) -> object:
        values: dict[str, object] = {
            "server_major": 17,
            "alembic_revision": "0001_foundation_runtime",
            "extensions": {"postgis", "vector"},
        }
        if self.failure == "postgres.server_major" and operation == "server_major":
            return 16
        if (
            self.failure == "postgres.alembic_revision"
            and operation == "alembic_revision"
        ):
            return "wrong-revision"
        if self.failure == "postgres.extensions" and operation == "extensions":
            return {"postgis"}
        return values[operation]

    def redis(self, operation: str, value: bytes | None = None) -> object:
        if operation == "ping":
            if self.failure == "redis.round_trip":
                return ""
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
            if self.failure == "object_store.round_trip":
                return {"size_bytes": 0}
            self.objects[(bucket, key)] = body
            return {"size_bytes": len(body)}
        if operation == "stat":
            return {"size_bytes": len(self.objects[(bucket, key)])}
        if operation == "get":
            return self.objects[(bucket, key)]
        raise AssertionError(operation)

    def http(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> object:
        self.http_requests.append((method, url, headers, body))
        if self.failure == "grafana.otlp" and "otel" in url:
            return 503
        if "sentry" in url:
            if self.failure == "sentry.event":
                return {"status_code": 202}
            return {"status_code": 202, "event_id": "evt-preview-probe"}
        if self.failure == "supabase.reachability" and "supabase" in url:
            return 503
        if self.failure == "resend.reachability" and "resend" in url:
            return 503
        return 200


def _config() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql://umbral:umbral@preview-postgres.railway.internal:5432/railway",
        "OBJECT_STORE_BUCKET": "umbral-primary",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.test",
        "SENTRY_DSN": "https://sentry-secret@sentry.example.test/42",
        "SUPABASE_URL": "https://configured-project.supabase.co",
        "IDENTITY_ISSUER": "https://configured-project.supabase.co/auth/v1",
        "SUPABASE_SECRET_KEY": "sb_secret_test_value",
        "RESEND_API_KEY": "re_test_value",
    }


def test_preview_dependency_gate_runs_all_remote_checks_without_secret_evidence() -> (
    None
):
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
        "redis.round_trip",
        "object_store.round_trip",
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


@pytest.mark.parametrize(
    "failure",
    [
        "postgres.server_major",
        "postgres.alembic_revision",
        "postgres.extensions",
        "redis.round_trip",
        "object_store.round_trip",
        "grafana.otlp",
        "sentry.event",
        "supabase.issuer",
        "supabase.reachability",
        "resend.reachability",
    ],
)
def test_preview_dependency_gate_fails_closed_without_sensitive_evidence(
    failure: str,
) -> None:
    from umbral.ops.provider_conformance import (
        PreviewDependencyClients,
        run_preview_dependency_conformance,
    )

    config = _config()
    if failure == "supabase.issuer":
        config["IDENTITY_ISSUER"] = "https://wrong-issuer.example.test/auth/v1"
    clients = _Clients(failure)

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
    assert next(check for check in report.checks if check.name == failure).code == (
        "dependency.failed"
    )
    assert "runtime" not in repr(report.to_dict())
    assert "sentry-secret" not in repr(report.to_dict())
    assert "re_test_value" not in repr(report.to_dict())


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


def test_release_manifest_revision_matches_alembic_head() -> None:
    """The release manifest must expect the schema produced by upgrade head."""
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    heads = ScriptDirectory.from_config(config).get_heads()

    assert len(heads) == 1
    assert f'-DatabaseRevision "{heads[0]}"' in workflow


def test_promotion_bootstraps_locked_uv_before_linux_python_deployment_steps() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    workflow = (repository_root / ".github" / "workflows" / "promote.yml").read_text(
        encoding="utf-8"
    )
    migrate_path = repository_root / "scripts" / "deploy" / "migrate-preview.ps1"
    migrate = migrate_path.read_text(encoding="utf-8")
    conformance = (
        repository_root / "scripts" / "deploy" / "check-preview-dependencies.ps1"
    ).read_text(encoding="utf-8")
    smoke = (repository_root / "scripts" / "deploy" / "smoke.ps1").read_text(
        encoding="utf-8"
    )

    setup = "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"
    assert setup in workflow
    assert 'version: "0.8.17"' in workflow
    assert "uv sync --locked --all-groups" in workflow
    assert workflow.index("uv sync --locked --all-groups") < workflow.index(
        "migrate-preview.ps1"
    )
    assert ".venv/bin/python" in workflow
    assert "PythonExecutable" in migrate
    assert "PythonExecutable" in conformance
    assert "PythonExecutable" in smoke
