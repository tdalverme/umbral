"""Local smoke and recovery gates (T101/T103)."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from umbral.ops.backup import BackupManifest, BackupPolicy
from umbral.ops.recovery_gate import evaluate_recovery_gate
from umbral.ops.smoke import run_smoke

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROMOTE_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "promote-release.ps1"
SET_IMAGES_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "set-railway-images.ps1"
WAIT_SERVICES_SCRIPT = (
    REPOSITORY_ROOT / "scripts" / "deploy" / "wait-railway-services.ps1"
)
SMOKE_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "smoke.ps1"


def _release_manifest(path: Path) -> str:
    payload = {
        "schema_version": 1,
        "release_id": "2026.08.01-immutable",
        "git_sha": "a" * 40,
        "built_at": "2026-08-01T00:00:00+00:00",
        "contract_major": 1,
        "database_revision": "0001_foundation_runtime",
        "config_schema_version": 1,
        "artifacts": {
            "web": {
                "image": "ghcr.io/example/umbral/web",
                "digest": "sha256:" + "1" * 64,
                "platform": "linux/amd64",
            },
            "runtime": {
                "image": "ghcr.io/example/umbral/runtime",
                "digest": "sha256:" + "2" * 64,
                "platform": "linux/amd64",
            },
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_railway_cli(directory: Path) -> Path:
    fake = directory / "npx.cmd"
    fake.write_text(
        """@echo off
setlocal EnableDelayedExpansion
echo %*>> \"%FAKE_RAILWAY_LOG%\"
set service=
:next
if \"%~1\"==\"\" goto done
if \"%~1\"==\"--service-config\" set service=%~2
if \"%~1\"==\"--service\" set service=%~2
shift
goto next
:done
echo %* | findstr /C:\"service status\" >nul
if not errorlevel 1 (
  echo [{\"name\":\"web\",\"id\":\"svc-web\"},{\"name\":\"api\",\"id\":\"svc-api\"},{\"name\":\"worker\",\"id\":\"svc-worker\"},{\"name\":\"scheduler\",\"id\":\"svc-scheduler\"},{\"name\":\"model\",\"id\":\"svc-model\"}]
  exit /b 0
)
echo %* | findstr /C:\"deployment list\" >nul
if not errorlevel 1 (
  if exist \"%FAKE_RAILWAY_STATE%\" set /p count=<\"%FAKE_RAILWAY_STATE%\"
  if \"!count!\"==\"\" set count=0
  set /a count+=1
  > \"%FAKE_RAILWAY_STATE%\" echo !count!
  set body=
  for /l %%i in (1,1,!count!) do (
    if not \"!body!\"==\"\" set body=!body!,
    set body=!body!{\"id\":\"deployment-!service!-%%i\",\"status\":\"SUCCESS\"}
  )
  echo [!body!]
  exit /b 0
)
echo %* | findstr /C:\"environment edit\" >nul
if not errorlevel 1 (
  set /p input=
  echo STDIN:%input%>> \"%FAKE_RAILWAY_LOG%\"
  if not \"%FAKE_RAILWAY_EDIT_RESPONSE%\"==\"\" (
    echo %FAKE_RAILWAY_EDIT_RESPONSE%
    exit /b 0
  )
  echo {\"committed\":true}
  if not \"%FAKE_RAILWAY_EDIT_FAIL%\"==\"\" exit /b 1
)
echo %* | findstr /C:\"environment config\" >nul
if not errorlevel 1 (
  echo {}
  exit /b 0
)
echo {\"deploymentId\":\"deployment-!service!\"}
""",
        encoding="utf-8",
    )
    return fake


def _promotion_command(manifest: Path, checksum: str, evidence: Path) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-File",
        str(PROMOTE_SCRIPT),
        "-ManifestPath",
        str(manifest),
        "-ManifestSha256",
        checksum,
        "-Environment",
        "preview",
        "-AccessPassed",
        "-BackupPassed",
        "-MigrationPassed",
        "-SmokePassed",
        "-EvidencePath",
        str(evidence),
    ]


def _switch_command(manifest: Path, checksum: str) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-File",
        str(SET_IMAGES_SCRIPT),
        "-ManifestPath",
        str(manifest),
        "-ManifestSha256",
        checksum,
        "-Environment",
        "preview",
    ]


def _railway_env(
    tmp_path: Path, invocation_log: Path, **extra: str
) -> dict[str, str]:
    """Environment the promote scripts expect from the CI runner."""
    values = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel:4318",
        "SENTRY_DSN": "https://sentry@example.invalid/1",
        "OBJECT_STORE_BUCKET": "umbral-preview",
        "OBJECT_STORE_ENDPOINT_URL": "https://objects.example.invalid",
        "OBJECT_STORE_ACCESS_KEY": "object-key",
        "OBJECT_STORE_SECRET_KEY": "object-secret",
        "RESEND_API_KEY": "resend-key",
        "RESEND_FROM_EMAIL": "radar@example.invalid",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_SECRET_KEY": "supabase-key",
        "IDENTITY_ISSUER": "https://project.supabase.co/auth/v1",
        "EMAIL_WEBHOOK_SECRET": "webhook-secret",
        "UMBRAL_PREVIEW_BASE_URL": "preview.umbral.invalid",
        "MODEL_GATEWAY_OPENAI_API_KEY": "model-key",
        "MODEL_GATEWAY_SHARED_KEY": "model-shared-key",
    }
    values.update(extra)
    return os.environ | {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "FAKE_RAILWAY_LOG": str(invocation_log),
        "FAKE_RAILWAY_STATE": str(tmp_path / "railway-state.txt"),
        "RAILWAY_TOKEN": "project-token",
        **values,
    }


def _manifest(created_at: datetime, *, locked: bool = True) -> BackupManifest:
    return BackupManifest(
        backup_id="backup-test",
        created_at=created_at,
        source_namespace="primary",
        retention_until=created_at + timedelta(days=35),
        objects=(),
        database_dump_sha256=None,
        policy=BackupPolicy(),
        locked=locked,
    )


def test_smoke_requires_all_closed_checks_and_never_uses_product_data() -> None:
    names = (
        "web",
        "api",
        "worker",
        "scheduler",
        "extensions",
        "reference_job",
        "synthetic_object",
    )
    report = run_smoke({name: lambda: True for name in names})

    assert report.passed
    assert not report.product_data_used


def test_recovery_gate_enforces_rpo_lock_and_retention() -> None:
    created = datetime(2026, 7, 29, tzinfo=timezone.utc)
    assert evaluate_recovery_gate(
        _manifest(created), now=created + timedelta(hours=12)
    ).passed
    assert not evaluate_recovery_gate(
        _manifest(created), now=created + timedelta(hours=25)
    ).passed
    assert not evaluate_recovery_gate(
        _manifest(created, locked=False), now=created + timedelta(hours=1)
    ).passed


def test_promotion_switches_each_service_uses_exact_images_and_records_deployments(
    tmp_path: Path,
) -> None:
    """Dropping a digest, runtime service, or deployment wait must fail this flow."""
    manifest = tmp_path / "release-manifest.json"
    checksum = _release_manifest(manifest)
    evidence = tmp_path / "promotion-evidence.json"
    invocation_log = tmp_path / "railway.log"
    _fake_railway_cli(tmp_path)
    environment = _railway_env(
        tmp_path,
        invocation_log,
        RAILWAY_TOKEN="project-token-that-must-not-leak",
        PROVIDER_SECRET="provider-value-that-must-not-leak",
    )

    completed = subprocess.run(
        _promotion_command(manifest, checksum, evidence),
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    output = completed.stdout + completed.stderr
    assert "project-token-that-must-not-leak" not in output
    assert "provider-value-that-must-not-leak" not in output
    calls = invocation_log.read_text(encoding="utf-8")
    assert "environment edit -e preview -m 2026.08.01-immutable" in calls
    assert "service status --all -e preview --json" in calls
    # 5 services x known+new deployment queries, plus the wait pass over the
    # four waited services.
    assert calls.count("deployment list") == 14
    deployed = json.loads(evidence.read_text(encoding="utf-8"))
    assert deployed["deployed"] is True
    assert deployed["manifest_sha256"] == checksum
    assert set(deployed["deployment_ids"]) == {
        "web",
        "api",
        "worker",
        "scheduler",
        "model",
    }
    assert all(
        value.startswith("deployment-") for value in deployed["deployment_ids"].values()
    )


def test_promotion_rejects_an_invalid_manifest_checksum_before_calling_railway(
    tmp_path: Path,
) -> None:
    """A tampered manifest must not reach an image switch."""
    manifest = tmp_path / "release-manifest.json"
    _release_manifest(manifest)
    invocation_log = tmp_path / "railway.log"
    _fake_railway_cli(tmp_path)
    environment = os.environ | {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "FAKE_RAILWAY_LOG": str(invocation_log),
        "RAILWAY_TOKEN": "project-token",
    }

    completed = subprocess.run(
        _promotion_command(manifest, "0" * 64, tmp_path / "evidence.json"),
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "checksum" in (completed.stdout + completed.stderr).lower()
    assert not invocation_log.exists()


def test_promotion_rejects_manifest_schema_drift_before_calling_railway(
    tmp_path: Path,
) -> None:
    """An unrecognized artifact property must not silently reach Railway."""
    manifest = tmp_path / "release-manifest.json"
    _release_manifest(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"]["web"]["unexpected"] = True
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    checksum = hashlib.sha256(manifest.read_bytes()).hexdigest()
    invocation_log = tmp_path / "railway.log"
    _fake_railway_cli(tmp_path)

    completed = subprocess.run(
        _promotion_command(manifest, checksum, tmp_path / "evidence.json"),
        cwd=REPOSITORY_ROOT,
        env=os.environ
        | {
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "FAKE_RAILWAY_LOG": str(invocation_log),
            "RAILWAY_TOKEN": "project-token",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "schema" in (completed.stdout + completed.stderr).lower()
    assert not invocation_log.exists()


def test_railway_image_switch_rejects_uncommitted_edit(
    tmp_path: Path,
) -> None:
    """An environment edit that reports committed=false must fail closed."""
    manifest = tmp_path / "release-manifest.json"
    checksum = _release_manifest(manifest)
    _fake_railway_cli(tmp_path)

    completed = subprocess.run(
        _switch_command(manifest, checksum),
        cwd=REPOSITORY_ROOT,
        env=_railway_env(
            tmp_path,
            tmp_path / "railway.log",
            FAKE_RAILWAY_EDIT_RESPONSE='{"committed":false}',
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "did not commit" in (completed.stdout + completed.stderr)


def test_railway_image_switch_rejects_failed_edit(
    tmp_path: Path,
) -> None:
    """A nonzero exit from the environment edit must fail closed."""
    manifest = tmp_path / "release-manifest.json"
    checksum = _release_manifest(manifest)
    _fake_railway_cli(tmp_path)

    completed = subprocess.run(
        _switch_command(manifest, checksum),
        cwd=REPOSITORY_ROOT,
        env=_railway_env(
            tmp_path,
            tmp_path / "railway.log",
            FAKE_RAILWAY_EDIT_FAIL="1",
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "environment update failed" in (completed.stdout + completed.stderr)


def test_railway_wait_rejects_skipped_deployment_without_waiting(
    tmp_path: Path,
) -> None:
    """A skipped exact deployment is terminal and must not consume the timeout."""
    (tmp_path / "npx.cmd").write_text(
        "@echo [{\"id\":\"deployment-web\",\"status\":\"SKIPPED\"}]\r\n",
        encoding="utf-8",
    )
    deployment_ids = json.dumps(
        {
            "web": "deployment-web",
            "api": "deployment-api",
            "worker": "deployment-worker",
            "scheduler": "deployment-scheduler",
        }
    )

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(WAIT_SERVICES_SCRIPT),
            "-Environment",
            "preview",
            "-DeploymentIdsJson",
            deployment_ids,
            "-TimeoutSeconds",
            "1",
            "-PollSeconds",
            "1",
        ],
        cwd=REPOSITORY_ROOT,
        env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "SKIPPED" in (completed.stdout + completed.stderr)


def test_smoke_accepts_an_absolute_manifest_path() -> None:
    """Artifact download paths are absolute when handed from workflow PowerShell."""
    manifest = (
        REPOSITORY_ROOT
        / "tests"
        / "fixtures"
        / "release-manifests"
        / "valid.json"
    )

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(SMOKE_SCRIPT),
            "-ManifestPath",
            str(manifest),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
