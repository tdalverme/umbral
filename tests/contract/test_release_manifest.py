"""Release manifest and surface identity contracts (T084)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from umbral.ops.release import InvalidReleaseManifest, ReleaseManifest


def valid_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "release_id": "2026.07.29-abc1234",
        "git_sha": "a" * 40,
        "built_at": datetime(2026, 7, 29, tzinfo=timezone.utc).isoformat(),
        "contract_major": 1,
        "database_revision": "0001_foundation_runtime",
        "config_schema_version": 1,
        "artifacts": {
            "web": {
                "image": "ghcr.io/umbral/web",
                "digest": "sha256:" + "1" * 64,
                "platform": "linux/amd64",
            },
            "runtime": {
                "image": "ghcr.io/umbral/runtime",
                "digest": "sha256:" + "2" * 64,
                "platform": "linux/amd64",
            },
        },
    }


def test_manifest_is_canonical_and_checksum_is_stable() -> None:
    first = ReleaseManifest.from_mapping(valid_manifest())
    reordered = dict(reversed(list(valid_manifest().items())))
    second = ReleaseManifest.from_mapping(reordered)

    assert first.canonical_json() == second.canonical_json()
    assert len(first.checksum_sha256()) == 64
    assert first.artifact_digests() == {
        "web": "sha256:" + "1" * 64,
        "runtime": "sha256:" + "2" * 64,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("git_sha", "not-a-sha"),
        ("contract_major", 2),
        ("artifacts", {"web": {}, "runtime": {}}),
    ],
)
def test_manifest_rejects_invalid_identity(field: str, value: object) -> None:
    payload = valid_manifest()
    payload[field] = value

    with pytest.raises(InvalidReleaseManifest):
        ReleaseManifest.from_mapping(payload)


def test_surfaces_require_the_same_manifest_and_exact_digests() -> None:
    manifest = ReleaseManifest.from_mapping(valid_manifest())

    assert manifest.validate_surfaces(
        {
            "web": {
                "manifest_sha256": manifest.checksum_sha256(),
                "artifact_digest": "sha256:" + "1" * 64,
            },
            "api": {
                "manifest_sha256": manifest.checksum_sha256(),
                "artifact_digest": "sha256:" + "2" * 64,
            },
            "worker": {
                "manifest_sha256": manifest.checksum_sha256(),
                "artifact_digest": "sha256:" + "2" * 64,
            },
            "scheduler": {
                "manifest_sha256": manifest.checksum_sha256(),
                "artifact_digest": "sha256:" + "2" * 64,
            },
        }
    )
    assert not manifest.validate_surfaces(
        {
            "web": {
                "manifest_sha256": "0" * 64,
                "artifact_digest": "sha256:" + "1" * 64,
            }
        }
    )


def test_railway_contract_uses_the_manifest_artifact_names() -> None:
    """A renamed release artifact must not silently disconnect Railway services."""
    repository_root = Path(__file__).resolve().parents[2]
    fixture_path = (
        repository_root / "tests" / "fixtures" / "release-manifests" / "valid.json"
    )
    manifest = ReleaseManifest.from_mapping(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )
    services_path = repository_root / "infra" / "railway" / "services.json"
    services = json.loads(services_path.read_text(encoding="utf-8"))["services"]

    assert {service["release_artifact"] for service in services} == set(
        manifest.artifact_digests()
    )
