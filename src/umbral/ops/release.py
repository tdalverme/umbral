"""Pure release-manifest and promotion contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class InvalidReleaseManifest(ValueError):
    """Raised when an immutable release manifest fails its contract."""


class PromotionRejected(ValueError):
    """Raised when a release gate is missing or fails."""


_RELEASE_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARTIFACT_KEYS = {"image", "digest", "platform", "provenance"}
_MANIFEST_KEYS = {
    "schema_version",
    "release_id",
    "git_sha",
    "built_at",
    "contract_major",
    "database_revision",
    "config_schema_version",
    "artifacts",
}


def _required_text(payload: Mapping[str, object], name: str, *, max_length: int) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise InvalidReleaseManifest(f"invalid {name}")
    return value


@dataclass(frozen=True)
class Artifact:
    image: str
    digest: str
    platform: str
    provenance: str | None = None

    @classmethod
    def from_mapping(cls, payload: object) -> "Artifact":
        if not isinstance(payload, Mapping) or set(payload) - _ARTIFACT_KEYS:
            raise InvalidReleaseManifest("invalid artifact fields")
        image = _required_text(payload, "image", max_length=300)
        digest = _required_text(payload, "digest", max_length=100)
        platform = payload.get("platform")
        if not _DIGEST.fullmatch(digest) or platform != "linux/amd64":
            raise InvalidReleaseManifest("invalid artifact identity")
        provenance = payload.get("provenance")
        if provenance is not None and not isinstance(provenance, str):
            raise InvalidReleaseManifest("invalid artifact provenance")
        return cls(image=image, digest=digest, platform=platform, provenance=provenance)

    def to_mapping(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "image": self.image,
            "digest": self.digest,
            "platform": self.platform,
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance
        return payload


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: int
    release_id: str
    git_sha: str
    built_at: str
    contract_major: int
    database_revision: str
    config_schema_version: int
    artifacts: Mapping[str, Artifact]

    @classmethod
    def from_mapping(cls, payload: object) -> "ReleaseManifest":
        if not isinstance(payload, Mapping) or set(payload) != _MANIFEST_KEYS:
            raise InvalidReleaseManifest("manifest fields must match the schema")
        if payload.get("schema_version") != 1 or payload.get("contract_major") != 1:
            raise InvalidReleaseManifest("unsupported manifest version")
        release_id = _required_text(payload, "release_id", max_length=100)
        git_sha = _required_text(payload, "git_sha", max_length=40)
        database_revision = _required_text(payload, "database_revision", max_length=64)
        if not _RELEASE_ID.fullmatch(release_id) or not _GIT_SHA.fullmatch(git_sha):
            raise InvalidReleaseManifest("invalid release identity")
        built_at = _required_text(payload, "built_at", max_length=64)
        try:
            parsed_built_at = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidReleaseManifest("invalid built_at") from exc
        if parsed_built_at.tzinfo is None:
            raise InvalidReleaseManifest("built_at must include timezone")
        config_schema_version = payload.get("config_schema_version")
        if not isinstance(config_schema_version, int) or config_schema_version < 1:
            raise InvalidReleaseManifest("invalid config schema version")
        artifacts_payload = payload.get("artifacts")
        if (
            not isinstance(artifacts_payload, Mapping)
            or set(artifacts_payload) != {"web", "runtime"}
        ):
            raise InvalidReleaseManifest("web and runtime artifacts are required")
        artifacts = {
            name: Artifact.from_mapping(artifact)
            for name, artifact in artifacts_payload.items()
        }
        return cls(
            schema_version=1,
            release_id=release_id,
            git_sha=git_sha,
            built_at=built_at,
            contract_major=1,
            database_revision=database_revision,
            config_schema_version=config_schema_version,
            artifacts=artifacts,
        )

    @classmethod
    def load(cls, path: str) -> "ReleaseManifest":
        with open(path, encoding="utf-8") as handle:
            return cls.from_mapping(json.load(handle))

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "release_id": self.release_id,
            "git_sha": self.git_sha,
            "built_at": self.built_at,
            "contract_major": self.contract_major,
            "database_revision": self.database_revision,
            "config_schema_version": self.config_schema_version,
            "artifacts": {
                name: self.artifacts[name].to_mapping() for name in ("web", "runtime")
            },
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_mapping(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def checksum_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def artifact_digests(self) -> dict[str, str]:
        return {name: artifact.digest for name, artifact in self.artifacts.items()}

    def validate_surfaces(self, surfaces: Mapping[str, Mapping[str, object]]) -> bool:
        if set(surfaces) != {"web", "api", "worker", "scheduler"}:
            return False
        manifest_checksum = self.checksum_sha256()
        expected = self.artifact_digests()
        for surface, status in surfaces.items():
            if status.get("manifest_sha256") != manifest_checksum:
                return False
            expected_digest = (
                expected["web"] if surface == "web" else expected["runtime"]
            )
            if status.get("artifact_digest") != expected_digest:
                return False
        return True


@dataclass
class PromotionPlan:
    manifest: ReleaseManifest
    environment: str
    completed_gates: tuple[str, ...] = ()

    def run_gates(
        self, *, access: bool, backup: bool, migration: bool, smoke: bool
    ) -> bool:
        gates = (
            ("access", access),
            ("backup", backup),
            ("migration", migration),
            ("smoke", smoke),
        )
        for name, passed in gates:
            if not passed:
                raise PromotionRejected(f"{name} gate failed")
        self.completed_gates = tuple(name for name, _ in gates)
        return True


def build_manifest(**payload: Any) -> ReleaseManifest:
    """Validate a mapping assembled by a build job without adding side effects."""

    return ReleaseManifest.from_mapping(payload)
