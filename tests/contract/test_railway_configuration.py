"""Railway preview service contract checks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICES_PATH = REPOSITORY_ROOT / "infra" / "railway" / "services.json"
VARIABLES_PATH = REPOSITORY_ROOT / "infra" / "railway" / "variables.example.json"
RUNTIME_DOCKERFILE = REPOSITORY_ROOT / "Dockerfile.runtime"
VALID_MANIFEST_PATH = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "release-manifests" / "valid.json"
)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def services_by_name() -> dict[str, dict[str, object]]:
    payload = load_json(SERVICES_PATH)
    services = payload["services"]
    assert isinstance(services, list)
    return {service["name"]: service for service in services}


@pytest.mark.parametrize(
    (
        "name",
        "artifact",
        "start_command",
        "public",
        "healthcheck_path",
        "restart_policy",
    ),
    [
        ("web", "web", None, True, "/health", "ON_FAILURE"),
        (
            "api",
            "runtime",
            "python -m uvicorn umbral.api.main:app --host 0.0.0.0 --port 8000",
            False,
            "/health",
            "ON_FAILURE",
        ),
        ("worker", "runtime", "python -m umbral.workers worker", False, None, "ALWAYS"),
        (
            "scheduler",
            "runtime",
            "python -m umbral.workers scheduler-once",
            False,
            None,
            "NEVER",
        ),
    ],
)
def test_service_contract_preserves_preview_process_boundaries(
    name: str,
    artifact: str,
    start_command: str | None,
    public: bool,
    healthcheck_path: str | None,
    restart_policy: str,
) -> None:
    """A wrong image, command, exposure, or restart policy must fail review."""
    service = services_by_name()[name]

    assert service["release_artifact"] == artifact
    assert service.get("start_command") == start_command
    assert service["public_domain"] is public
    assert service.get("healthcheck_path") == healthcheck_path
    assert service["restart_policy"] == restart_policy


def test_cron_and_sleep_policies_preserve_beta_cost_and_availability() -> None:
    """A too-frequent cron or sleeping worker would break preview topology."""
    services = services_by_name()

    assert services["scheduler"]["cron_schedule"] == "*/5 * * * *"
    assert services["scheduler"]["cron_timezone"] == "UTC"
    assert services["web"]["serverless_sleep"] is True
    assert services["api"]["serverless_sleep"] is True
    assert services["worker"]["serverless_sleep"] is False
    assert {
        services[name]["release_artifact"] for name in ("api", "worker", "scheduler")
    } == {"runtime"}


def test_runtime_image_has_a_safe_default_command_for_service_overrides() -> None:
    """A worker-only entrypoint would prevent API and cron commands from starting."""
    dockerfile = RUNTIME_DOCKERFILE.read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "umbral.workers", "--help"]' in dockerfile
    assert "ENTRYPOINT" not in dockerfile


def test_runtime_image_copies_alembic_assets_to_the_runtime_path() -> None:
    """A flattened Alembic copy would make migration assets unavailable at runtime."""
    dockerfile = RUNTIME_DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY alembic ./alembic" in dockerfile


def test_variable_inventory_contains_only_scoped_variable_names() -> None:
    """A sample credential value or unscoped secret would make the inventory unsafe."""
    inventory = load_json(VARIABLES_PATH)
    variables = inventory["variables"]
    assert isinstance(variables, list)

    names = {variable["name"] for variable in variables}
    assert {
        "UMBRAL_PRIVATE_API_URL",
        "UMBRAL_BFF_TOKEN",
        "DATABASE_URL",
        "REDIS_URL",
        "OBJECT_STORE_ACCESS_KEY",
        "SUPABASE_SECRET_KEY",
        "RESEND_API_KEY",
        "GHCR_DEPLOY_TOKEN",
        "RAILWAY_TOKEN",
    } <= names
    assert all(set(variable) == {"name", "scopes"} for variable in variables)
    assert all(variable["scopes"] for variable in variables)


def test_railway_validator_resolves_contract_artifacts_from_release_manifest() -> None:
    """A manifest with immutable digests must validate the service contract."""
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(REPOSITORY_ROOT / "scripts" / "deploy" / "validate-railway-config.ps1"),
            "-ManifestPath",
            str(VALID_MANIFEST_PATH),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "web=sha256:" in completed.stdout
    assert "runtime=sha256:" in completed.stdout
