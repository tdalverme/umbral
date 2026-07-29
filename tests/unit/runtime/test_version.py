"""Behavioral contract for local immutable release manifests."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from umbral.application.runtime.version import (
    ReleaseManifestValidationError,
    load_release_manifest,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = ROOT / "tests" / "fixtures" / "release-manifests"


def test_load_release_manifest_returns_an_immutable_release_value() -> None:
    release = load_release_manifest(MANIFESTS / "valid.json")

    assert release.release_id == "foundation-20260101"
    assert release.git_sha == "0123456789abcdef0123456789abcdef01234567"
    assert release.artifacts["runtime"].digest == (
        "sha256:2222222222222222222222222222222222222222222222222222222222222222"
    )
    with pytest.raises(FrozenInstanceError):
        release.release_id = "mutable"  # type: ignore[misc]


@pytest.mark.parametrize(
    "fixture_name",
    [
        "invalid-digest.json",
        "invalid-platform.json",
        "invalid-extra-property.json",
        "invalid-missing-required.json",
    ],
)
def test_load_release_manifest_rejects_each_invalid_schema_fixture(
    fixture_name: str,
) -> None:
    with pytest.raises(ReleaseManifestValidationError) as raised:
        load_release_manifest(MANIFESTS / fixture_name)

    assert "manifest" in str(raised.value).lower()


@pytest.mark.parametrize(
    ("field_path", "invalid_value", "expected_field"),
    [
        (("built_at",), "2026-01-01T00:00:00", "built_at"),
        (("schema_version",), True, "schema_version"),
        (("contract_major",), True, "contract_major"),
        (("config_schema_version",), True, "config_schema_version"),
        (("database_revision",), "x" * 65, "database_revision"),
        (("artifacts", "web", "image"), "", "artifacts.web.image"),
    ],
)
def test_load_release_manifest_rejects_schema_drift_from_valid_fixture(
    tmp_path: Path,
    field_path: tuple[str, ...],
    invalid_value: object,
    expected_field: str,
) -> None:
    manifest = json.loads((MANIFESTS / "valid.json").read_text(encoding="utf-8"))
    target: dict[str, Any] = manifest
    for field_name in field_path[:-1]:
        target = target[field_name]
    target[field_path[-1]] = invalid_value
    path = tmp_path / "release-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ReleaseManifestValidationError) as raised:
        load_release_manifest(path)

    assert raised.value.field_name == expected_field
