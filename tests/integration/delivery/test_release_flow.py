"""Local release promotion flow contracts (T086)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from umbral.ops.release import ReleaseManifest
from umbral.ops.release_lock import ReleaseLock, ReleaseLockBusy

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROMOTE_SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy" / "promote-release.ps1"
PROMOTE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "promote.yml"


def _manifest(path: Path) -> str:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_id": "r1",
                "git_sha": "a" * 40,
                "built_at": "2026-07-29T00:00:00+00:00",
                "contract_major": 1,
                "database_revision": "0001_foundation_runtime",
                "config_schema_version": 1,
                "artifacts": {
                    "web": {
                        "image": "ghcr.io/example/web",
                        "digest": "sha256:" + "1" * 64,
                        "platform": "linux/amd64",
                    },
                    "runtime": {
                        "image": "ghcr.io/example/runtime",
                        "digest": "sha256:" + "2" * 64,
                        "platform": "linux/amd64",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_environment_lock_is_create_if_absent_and_expires() -> None:
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    lock = ReleaseLock()

    lock.acquire(
        "preview",
        owner="ci-1",
        release_id="r1",
        now=now,
        ttl=timedelta(minutes=15),
    )
    with pytest.raises(ReleaseLockBusy):
        lock.acquire("preview", owner="ci-2", release_id="r2", now=now)

    lock.acquire(
        "preview",
        owner="ci-2",
        release_id="r2",
        now=now + timedelta(minutes=16),
    )
    assert lock.owner("preview", now=now + timedelta(minutes=16)) == "ci-2"


def test_promotion_requires_same_manifest_and_ordered_gates() -> None:
    from umbral.ops.release import PromotionPlan, PromotionRejected

    manifest = ReleaseManifest.from_mapping(
        {
            "schema_version": 1,
            "release_id": "r1",
            "git_sha": "a" * 40,
            "built_at": "2026-07-29T00:00:00+00:00",
            "contract_major": 1,
            "database_revision": "0001_foundation_runtime",
            "config_schema_version": 1,
            "artifacts": {
                "web": {
                    "image": "web",
                    "digest": "sha256:" + "1" * 64,
                    "platform": "linux/amd64",
                },
                "runtime": {
                    "image": "runtime",
                    "digest": "sha256:" + "2" * 64,
                    "platform": "linux/amd64",
                },
            },
        }
    )
    plan = PromotionPlan(manifest=manifest, environment="preview")

    assert plan.run_gates(access=True, backup=True, migration=True, smoke=True)
    with pytest.raises(PromotionRejected):
        plan.run_gates(access=True, backup=True, migration=True, smoke=False)


@pytest.mark.parametrize("missing_gate", ["access", "backup", "migration", "smoke"])
def test_failed_gate_aborts_before_the_railway_image_switch(
    tmp_path: Path, missing_gate: str
) -> None:
    """Allowing any failed gate to mutate Railway would deploy an unverified release."""
    manifest = tmp_path / "release-manifest.json"
    checksum = _manifest(manifest)
    fake_npx = tmp_path / "npx.cmd"
    fake_npx.write_text(
        "@echo called>> \"%FAKE_RAILWAY_LOG%\"\r\nexit /b 1\r\n",
        encoding="utf-8",
    )
    invocation_log = tmp_path / "railway.log"
    command = [
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
    ]
    for gate in ("Access", "Backup", "Migration", "Smoke"):
        if gate.lower() != missing_gate:
            command.append(f"-{gate}Passed")

    completed = subprocess.run(
        command,
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
    assert f"Promotion gate failed: {missing_gate}" in (
        completed.stdout + completed.stderr
    )
    assert not invocation_log.exists()


def test_config_gate_aborts_before_the_railway_image_switch(tmp_path: Path) -> None:
    """A Railway contract violation must fail before a service image is mutated."""
    manifest = tmp_path / "release-manifest.json"
    _manifest(manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"]["web"]["platform"] = "linux/arm64"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    checksum = hashlib.sha256(manifest.read_bytes()).hexdigest()
    invocation_log = tmp_path / "railway.log"
    fake_npx = tmp_path / "npx.cmd"
    fake_npx.write_text(
        "@echo called>> \"%FAKE_RAILWAY_LOG%\"\r\nexit /b 1\r\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
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
        ],
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
    assert "platform" in (completed.stdout + completed.stderr).lower()
    assert not invocation_log.exists()


def test_promotion_downloads_the_named_release_run_artifact() -> None:
    """A missing release run ID could select an unrelated latest artifact."""
    workflow = yaml.load(
        PROMOTE_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    download = next(
        step
        for step in workflow["jobs"]["promote"]["steps"]
        if step.get("uses") == "actions/download-artifact@v4"
    )

    assert workflow["permissions"]["actions"] == "read"
    assert inputs["release_run_id"]["required"] == "true"
    assert download["with"] == {
        "name": "${{ inputs.manifest }}",
        "path": "artifacts/release",
        "github-token": "${{ github.token }}",
        "run-id": "${{ inputs.release_run_id }}",
    }
