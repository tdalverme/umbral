"""Conformance of the published graph releases registry contract."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.golden import load_golden_dataset
from umbral.application.agent_evals.releases import (
    activation_allowed,
    load_releases,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "conversations-golden-v1.json"
RELEASES_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "graph-releases-v1.json"


def test_releases_reference_existing_cases_and_are_append_only() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    releases = load_releases(
        RELEASES_PATH, known_case_ids={case.id for case in dataset.cases}
    )
    assert releases.registry_version == "graph-releases-v1"
    active = releases.active_release()
    assert active is not None
    unknown = [
        case_id
        for release in releases.releases
        for case_id in release.affected_case_ids
        if dataset.case_by_id(case_id) is None
    ]
    assert not unknown


def test_releases_document_is_valid_json() -> None:
    raw = json.loads(RELEASES_PATH.read_text(encoding="utf-8"))
    assert raw["registry_version"] == "graph-releases-v1"
    assert isinstance(raw["releases"], list)


def test_active_release_activation_is_allowed() -> None:
    releases = load_releases(RELEASES_PATH)
    active = releases.active_release()
    assert active is not None
    assert activation_allowed(active) is True
