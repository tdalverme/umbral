"""Behavioral contract for local immutable release manifests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

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
