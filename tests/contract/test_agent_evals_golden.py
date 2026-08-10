"""Conformance of the published golden conversations dataset contract (US1)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.golden import load_golden_dataset

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "conversations-golden-v1.json"
SCHEMA_PATH = (
    ROOT / "contracts" / "agent-evals" / "v1" / "conversations-golden.schema.json"
)

_FAMILIES = frozenset(
    {
        "onboarding",
        "ambiguous_change",
        "explanation",
        "comparison",
        "feedback",
        "injection",
        "safe_refusal",
    }
)


def test_contract_document_matches_the_published_json() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    assert dataset.contract_version == "1"
    assert dataset.registry_version == "conversations-golden-v1"
    assert dataset.reviewed_by
    assert dataset.reviewed_at
    assert dataset.min_cases_per_family == 3
    assert len(dataset.cases) >= 21


def test_schema_document_is_valid_json() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$id"].endswith("conversations-golden.schema.json")
    assert schema["type"] == "object"
    assert "cases" in schema["properties"]
    assert set(schema["$defs"]["case"]["properties"]["family"]["enum"]) == _FAMILIES


def test_dataset_covers_all_families_with_minimum_count() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    for family in _FAMILIES:
        assert len(dataset.cases_for_family(family)) >= 3, family


def test_every_case_defines_a_complete_expectation() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    for case in dataset.cases:
        assert case.turns
        assert case.expectation.outcome in {
            "completed",
            "clarification",
            "safe_refusal",
            "failed",
        }
        for call in case.expectation.tool_calls:
            assert call.order >= 1
        grounding = case.expectation.grounding
        if grounding.require_refs:
            assert grounding.min_refs >= 1, case.id


def test_ambiguous_change_cases_require_clarification_before_any_proposal() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    for case in dataset.cases_for_family("ambiguous_change"):
        assert case.expectation.outcome == "clarification"
        assert not case.expectation.tool_calls


def test_injection_and_safe_refusal_cases_declare_the_limit_without_tools() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    for case in list(dataset.cases_for_family("injection")) + list(
        dataset.cases_for_family("safe_refusal")
    ):
        assert case.expectation.outcome == "safe_refusal"
        assert not case.expectation.tool_calls
