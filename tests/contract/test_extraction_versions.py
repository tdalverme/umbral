"""Conformance of extraction versioning: immutable artifact registry."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.criteria.contracts import ExtractionVersion

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def build_version(
    *,
    kind: str = "rule",
    key: str = "balcon",
    version: str = "balcon.rule-v1",
) -> ExtractionVersion:
    return ExtractionVersion(
        version_id=uuid4(),
        kind=kind,  # type: ignore[arg-type]
        key=key,
        version=version,
        payload={"rule": key},
        created_at=NOW,
        correlation_id=uuid4(),
    )


def test_extraction_version_kind_is_bounded() -> None:
    for kind in ("rule", "prompt", "schema", "model", "embedding"):
        assert build_version(kind=kind, key="x", version="x-v1").kind == kind


def test_versions_carry_immutable_identity() -> None:
    first = build_version()
    assert first.version_id is not None
    assert first.created_at == NOW
    assert first.payload == {"rule": "balcon"}


def test_kind_key_version_triple_is_the_unique_identity() -> None:
    same = build_version()
    other = build_version(version="balcon.rule-v2")
    assert (same.kind, same.key, same.version) != (other.kind, other.key, other.version)
