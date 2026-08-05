"""Local smoke and recovery gates (T101/T103)."""

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
if not "%FAKE_RAILWAY_EDIT_RESPONSE%"=="" (
  echo %FAKE_RAILWAY_EDIT_RESPONSE%
  exit /b 0
)
echo %* | findstr /C:\"deployment list\" >nul
if not errorlevel 1 (
  echo [{\"id\":\"deployment-!service!\",\"status\":\"SUCCESS\"}]
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
    environment = os.environ | {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "FAKE_RAILWAY_LOG": str(invocation_log),
        "RAILWAY_TOKEN": "project-token-that-must-not-leak",
        "PROVIDER_SECRET": "provider-value-that-must-not-leak",
    }

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
    assert (
        "source.image ghcr.io/example/umbral/web@sha256:" + "1" * 64
    ) in calls
    runtime_image = "source.image ghcr.io/example/umbral/runtime@sha256:" + "2" * 64
    assert calls.count(runtime_image) == 3
    assert calls.count("deployment list") == 4
    assert "variables.UMBRAL_RELEASE_ID.value 2026.08.01-immutable" in calls
    assert calls.count("variables.UMBRAL_RELEASE_DIGEST.value sha256:" + "1" * 64) == 1
    assert calls.count("variables.UMBRAL_RELEASE_DIGEST.value sha256:" + "2" * 64) == 3
    assert calls.count("variables.UMBRAL_RELEASE_MANIFEST.value") == 4
    assert "schema_version" in calls
    deployed = json.loads(evidence.read_text(encoding="utf-8"))
    assert deployed["deployed"] is True
    assert deployed["manifest_sha256"] == checksum
    assert deployed["deployment_ids"] == {
        "web": "deployment-web",
        "api": "deployment-api",
        "worker": "deployment-worker",
        "scheduler": "deployment-scheduler",
    }


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


def test_railway_image_switch_rejects_a_nested_deployment_id(
    tmp_path: Path,
) -> None:
    """A deployment ID outside the modeled top-level response is ambiguous."""
    manifest = tmp_path / "release-manifest.json"
    checksum = _release_manifest(manifest)
    _fake_railway_cli(tmp_path)

    completed = subprocess.run(
        _switch_command(manifest, checksum),
        cwd=REPOSITORY_ROOT,
        env=os.environ
        | {
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "RAILWAY_TOKEN": "project-token",
            "FAKE_RAILWAY_LOG": str(tmp_path / "railway.log"),
            "FAKE_RAILWAY_EDIT_RESPONSE": '{"operation":{"deploymentId":"nested"}}',
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "deployment ID" in (completed.stdout + completed.stderr)


def test_railway_image_switch_rejects_multiple_top_level_deployment_ids(
    tmp_path: Path,
) -> None:
    """Two explicit response IDs are no safer than selecting the latest deployment."""
    manifest = tmp_path / "release-manifest.json"
    checksum = _release_manifest(manifest)
    _fake_railway_cli(tmp_path)

    completed = subprocess.run(
        _switch_command(manifest, checksum),
        cwd=REPOSITORY_ROOT,
        env=os.environ
        | {
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "RAILWAY_TOKEN": "project-token",
            "FAKE_RAILWAY_LOG": str(tmp_path / "railway.log"),
            "FAKE_RAILWAY_EDIT_RESPONSE": (
                '{"deploymentId":"one","deployment_id":"two"}'
            ),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "deployment ID" in (completed.stdout + completed.stderr)


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
