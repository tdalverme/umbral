"""Conformance tests for the V4 eval contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import jsonschema  # type: ignore[import-untyped]
import pytest

from umbral.application.agent_evals.v4.loader import (
    EvalV4ValidationError,
    load_dataset,
    load_policy,
    load_releases,
)

ROOT = Path(__file__).resolve().parents[2]
V4_DIR = ROOT / "contracts" / "agent-evals" / "v4"


def _read(name: str) -> dict[str, object]:
    raw = json.loads((V4_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_dataset_schema_validates_the_published_file() -> None:
    schema = _read("conversation-trajectories-v4.schema.json")
    data = _read("conversation-trajectories-v4.json")
    jsonschema.validate(data, schema)


def test_dataset_covers_the_required_v5_families() -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    families = {case.family for case in dataset.cases}
    assert {
        "untrusted_provenance",
        "invalid_refs",
        "unsupported_request",
        "ambiguous_revision",
        "post_confirm_refresh",
        "partial_multi_act",
        "provider_failure",
        "reply_fallback",
        "idempotent_retry",
        "stale_context",
    } <= families
    for case in dataset.cases:
        assert case.review.reviewed_by
        assert case.review.reviewed_at
        assert case.review.rationale


def test_every_expected_status_is_a_published_outcome_status() -> None:
    dataset = load_dataset(V4_DIR / "conversation-trajectories-v4.json")
    allowed = {
        "applied",
        "pending",
        "rejected",
        "needs_clarification",
        "not_executed",
    }
    for case in dataset.cases:
        for turn in case.turns:
            assert set(turn.expected.outcome_statuses) <= allowed
            assert len(turn.expected.outcome_statuses) == len(
                turn.expected.reason_codes
            )


def test_policy_and_releases_load_with_expected_values() -> None:
    policy = load_policy(V4_DIR / "eval-policy-v4.json")
    assert policy.contract_version == "4"
    assert policy.scripted_trials == 1

    releases = load_releases(V4_DIR / "graph-releases-v3.json")
    by_id = {release.id: release for release in releases.releases}
    assert "graph-release-003" in by_id
    assert "graph-release-005" in by_id
    candidate = by_id["graph-release-005"]
    assert candidate.components.model_version == "gpt-4.1-mini"
    assert "interpretation" in candidate.components.prompt_versions
    assert "reply" in candidate.components.prompt_versions
    assert candidate.activation["status"] == "pending"


def test_loader_rejects_missing_component_files() -> None:
    with pytest.raises(EvalV4ValidationError):
        load_dataset(V4_DIR / "does-not-exist.json")


def test_dataset_schema_rejects_open_cases() -> None:
    schema = _read("conversation-trajectories-v4.schema.json")
    data = _read("conversation-trajectories-v4.json")
    cases = cast(list[dict[str, object]], data["cases"])
    case = dict(cases[0])
    case["unexpected"] = True
    cases[0] = case
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)