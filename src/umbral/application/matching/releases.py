"""Pure parsing and validation of the releases registry contract.

An explained change is declared in ``contracts/matching/v1/releases-v1.json``:
each entry names the artifact version, owner, justification and affected case
ids. The regression gate requires every detected order/hard-filter change to be
declared by a release whose affected cases match the diff (research R-02).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.matching.contracts import (
    MatchingValidationError,
    Release,
    ReleasesRegistry,
)

_KNOWN_ARTIFACTS: frozenset[str] = frozenset(
    {"scoring.policy", "criteria.concept", "extraction.rule", "extraction.prompt"}
)


def load_releases(path: Path) -> ReleasesRegistry:
    """Load and validate the releases registry from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise MatchingValidationError(("matching.releases_required",))
    return parse_releases(raw)


def parse_releases(
    data: Mapping[str, object], known_case_ids: frozenset[str] = frozenset()
) -> ReleasesRegistry:
    """Parse and validate the releases document; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("matching.unsupported_contract_version")
    if data.get("registry_version") != "matching-releases-v1":
        errors.append("matching.registry_version_required")
    raw_releases = data.get("releases")
    if not isinstance(raw_releases, list):
        errors.append("matching.releases_required")
        raw_releases = []
    releases: list[Release] = []
    seen_ids: set[str] = set()
    seen_versions: set[str] = set()
    for raw in raw_releases:
        if not isinstance(raw, Mapping):
            errors.append("matching.release_invalid_shape")
            continue
        release, release_errors = _parse_release(raw)
        if release_errors:
            errors.extend(release_errors)
            continue
        if release.id in seen_ids:
            errors.append(f"matching.duplicate_release:{release.id}")
        seen_ids.add(release.id)
        if release.artifact_version in seen_versions:
            errors.append(
                f"matching.duplicate_artifact_version:{release.artifact_version}"
            )
        seen_versions.add(release.artifact_version)
        if known_case_ids:
            unknown = [
                cid for cid in release.affected_case_ids if cid not in known_case_ids
            ]
            if unknown:
                errors.append(
                    f"matching.unknown_affected_case:{release.id}:{','.join(unknown)}"
                )
        releases.append(release)
    if errors:
        raise MatchingValidationError(tuple(sorted(set(errors))))
    return ReleasesRegistry(
        contract_version="1",
        registry_version="matching-releases-v1",
        releases=tuple(releases),
    )


def declared_affected(
    registry: ReleasesRegistry, artifact_version: str
) -> frozenset[str]:
    """Return the case ids a release declares as affected for a version."""
    return registry.affected_for(artifact_version)


def _parse_release(raw: Mapping[str, object]) -> tuple[Release, list[str]]:
    errors: list[str] = []
    release_id = _required_str(raw.get("id"), errors, "id")
    artifact = raw.get("artifact")
    if not isinstance(artifact, str) or artifact not in _KNOWN_ARTIFACTS:
        errors.append(f"matching.unknown_artifact:{artifact}")
    artifact_version = _required_str(
        raw.get("artifact_version"), errors, "artifact_version"
    )
    owner = _required_str(raw.get("owner"), errors, "owner")
    justification = _required_str(raw.get("justification"), errors, "justification")
    raw_cases = raw.get("affected_case_ids")
    affected = (
        tuple(str(item) for item in raw_cases) if isinstance(raw_cases, list) else ()
    )
    if not affected:
        errors.append("matching.affected_case_ids_required")
    date = _required_str(raw.get("date"), errors, "date")
    return (
        Release(
            id=release_id,
            artifact=str(artifact),
            artifact_version=artifact_version,
            owner=owner,
            justification=justification,
            affected_case_ids=affected,
            date=date,
        ),
        errors,
    )


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"matching.{field}_required")
        return ""
    return value
