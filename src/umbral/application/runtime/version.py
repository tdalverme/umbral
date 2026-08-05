"""Immutable values loaded from the release manifest shipped with a runtime."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlparse

_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}$")
_GIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}$")
_RELEASE_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}$")
_REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "release_id",
        "git_sha",
        "built_at",
        "contract_major",
        "database_revision",
        "config_schema_version",
        "artifacts",
    }
)


class ReleaseManifestValidationError(ValueError):
    """A safe diagnostic: it intentionally contains no manifest values."""

    def __init__(self, field_name: str) -> None:
        super().__init__(f"release manifest is invalid at {field_name}")
        self.field_name = field_name


@dataclass(frozen=True, slots=True)
class ReleaseArtifact:
    image: str
    digest: str
    platform: str
    provenance: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    release_id: str
    git_sha: str
    built_at: str
    contract_major: int
    database_revision: str
    config_schema_version: int
    artifacts: Mapping[str, ReleaseArtifact]
    manifest_sha256: str


def load_release_manifest(path: Path) -> ReleaseManifest:
    """Load one local manifest and reject data outside the checked-in contract."""

    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseManifestValidationError("document") from error
    return _parse_release_manifest(raw, sha256(raw_bytes).hexdigest())


def parse_release_manifest(text: str) -> ReleaseManifest:
    """Parse one inline JSON manifest, for example from UMBRAL_RELEASE_MANIFEST."""

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ReleaseManifestValidationError("document") from error
    return _parse_release_manifest(raw, sha256(text.encode("utf-8")).hexdigest())


def _parse_release_manifest(raw: Any, manifest_sha256: str) -> ReleaseManifest:
    if not isinstance(raw, dict):
        raise ReleaseManifestValidationError("document")
    _validate_manifest_fields(raw)

    artifacts_raw = _mapping(raw["artifacts"], "artifacts")
    if set(artifacts_raw) != {"web", "runtime"}:
        raise ReleaseManifestValidationError("artifacts")
    artifacts = {
        name: _release_artifact(value, f"artifacts.{name}")
        for name, value in artifacts_raw.items()
    }

    return ReleaseManifest(
        release_id=_string(raw["release_id"], "release_id"),
        git_sha=_string(raw["git_sha"], "git_sha"),
        built_at=_string(raw["built_at"], "built_at"),
        contract_major=_integer(raw["contract_major"], "contract_major"),
        database_revision=_string(raw["database_revision"], "database_revision"),
        config_schema_version=_integer(
            raw["config_schema_version"], "config_schema_version"
        ),
        artifacts=MappingProxyType(artifacts),
        manifest_sha256=manifest_sha256,
    )


def _validate_manifest_fields(raw: Mapping[str, Any]) -> None:
    if set(raw) != _REQUIRED_MANIFEST_FIELDS:
        raise ReleaseManifestValidationError("fields")
    if not _is_exact_integer(raw["schema_version"], 1):
        raise ReleaseManifestValidationError("schema_version")
    release_id = _string(raw["release_id"], "release_id")
    if not _RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ReleaseManifestValidationError("release_id")
    git_sha = _string(raw["git_sha"], "git_sha")
    if not _GIT_SHA_PATTERN.fullmatch(git_sha):
        raise ReleaseManifestValidationError("git_sha")
    built_at = _string(raw["built_at"], "built_at")
    try:
        timestamp = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReleaseManifestValidationError("built_at") from error
    offset = timestamp.utcoffset()
    if (
        timestamp.tzinfo is None
        or offset is None
        or offset.total_seconds() != 0
    ):
        raise ReleaseManifestValidationError("built_at")
    if not _is_exact_integer(raw["contract_major"], 1):
        raise ReleaseManifestValidationError("contract_major")
    database_revision = _string(raw["database_revision"], "database_revision")
    if not 1 <= len(database_revision) <= 64:
        raise ReleaseManifestValidationError("database_revision")
    if _integer(raw["config_schema_version"], "config_schema_version") < 1:
        raise ReleaseManifestValidationError("config_schema_version")


def _release_artifact(value: Any, field_name: str) -> ReleaseArtifact:
    raw = _mapping(value, field_name)
    permitted_fields = (
        {"image", "digest", "platform"},
        {"image", "digest", "platform", "provenance"},
    )
    if set(raw) not in permitted_fields:
        raise ReleaseManifestValidationError(field_name)
    image = _string(raw.get("image"), f"{field_name}.image")
    if not 1 <= len(image) <= 300:
        raise ReleaseManifestValidationError(f"{field_name}.image")
    digest = _string(raw.get("digest"), f"{field_name}.digest")
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise ReleaseManifestValidationError(f"{field_name}.digest")
    platform = _string(raw.get("platform"), f"{field_name}.platform")
    if platform != "linux/amd64":
        raise ReleaseManifestValidationError(f"{field_name}.platform")
    provenance: str | None = None
    if "provenance" in raw:
        provenance = _string(raw["provenance"], f"{field_name}.provenance")
        if not urlparse(provenance).scheme:
            raise ReleaseManifestValidationError(f"{field_name}.provenance")
    return ReleaseArtifact(
        image=image,
        digest=digest,
        platform=platform,
        provenance=provenance,
    )


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseManifestValidationError(field_name)
    return value


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ReleaseManifestValidationError(field_name)
    return value


def _integer(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReleaseManifestValidationError(field_name)
    return value


def _is_exact_integer(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected
