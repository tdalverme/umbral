"""Parser unit tests for the golden conversations dataset (T007)."""

from __future__ import annotations

from typing import Any

import pytest

from umbral.application.agent_evals.contracts import AgentEvalsValidationError
from umbral.application.agent_evals.golden import parse_golden_dataset


def _case(
    case_id: str, family: str, outcome: str, tool: str | None = None
) -> dict[str, Any]:
    tool_calls = (
        [{"tool": tool, "args": {}, "requires_confirmation": False, "order": 1}]
        if tool
        else []
    )
    require_refs = outcome == "completed" and tool is not None
    return {
        "id": case_id,
        "family": family,
        "context": {"profile": {"budget_max": 900000, "zone": "palermo"}},
        "turns": [f"mensaje de {case_id}"],
        "expectation": {
            "tool_calls": tool_calls,
            "grounding": {
                "require_refs": require_refs,
                "min_refs": 1 if require_refs else 0,
                "declare_missing": False,
            },
            "outcome": outcome,
        },
        "tags": ["rejects"] if outcome == "safe_refusal" else [],
        "notes": "fixture",
    }


def _dataset() -> dict[str, Any]:
    spec: list[tuple[str, str, str | None]] = [
        ("onboarding", "completed", "get_search_profile"),
        ("onboarding", "completed", "find_matches"),
        ("onboarding", "safe_refusal", None),
        ("ambiguous_change", "clarification", None),
        ("ambiguous_change", "clarification", None),
        ("ambiguous_change", "clarification", None),
        ("explanation", "completed", "explain_match"),
        ("explanation", "completed", "explain_match"),
        ("explanation", "completed", "explain_match"),
        ("comparison", "completed", "compare_listings"),
        ("comparison", "completed", "compare_listings"),
        ("comparison", "completed", "compare_listings"),
        ("feedback", "completed", "record_feedback"),
        ("feedback", "completed", "record_feedback"),
        ("feedback", "completed", "record_feedback"),
        ("injection", "safe_refusal", None),
        ("injection", "safe_refusal", None),
        ("injection", "safe_refusal", None),
("safe_refusal", "safe_refusal", None),
("safe_refusal", "safe_refusal", None),
("safe_refusal", "safe_refusal", None),
("preferences", "completed", "propose_search_preference_update"),
("preferences", "completed", "propose_search_preference_update"),
("preferences", "completed", "propose_search_preference_update"),
    ]
    return {
        "contract_version": "1",
        "registry_version": "conversations-golden-v1",
        "reviewed_by": "product-h4.4",
        "reviewed_at": "2026-08-10",
        "min_cases_per_family": 3,
        "cases": [
            _case(f"conversation-{index:03d}", family, outcome, tool)
            for index, (family, outcome, tool) in enumerate(spec, start=1)
        ],
    }


def test_golden_dataset_parses_with_full_coverage() -> None:
    dataset = parse_golden_dataset(_dataset())
    assert dataset.registry_version == "conversations-golden-v1"
    assert dataset.reviewed_by == "product-h4.4"
    assert len(dataset.cases) == 24
    assert len(dataset.cases_for_family("onboarding")) == 3
    assert dataset.case_by_id("conversation-001") is not None


def test_golden_dataset_rejects_duplicate_ids() -> None:
    data = _dataset()
    data["cases"] = [data["cases"][0], data["cases"][0]]
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_golden_dataset(data)
    assert any(
        "agent_evals.duplicate_case" in code for code in excinfo.value.error_codes
    )


def test_golden_dataset_rejects_unknown_family() -> None:
    data = _dataset()
    case = dict(data["cases"][0])
    case["family"] = "cooking"
    data["cases"] = [case] + list(data["cases"][1:])
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_golden_dataset(data)
    assert any(
        "agent_evals.unknown_family" in code for code in excinfo.value.error_codes
    )


def test_golden_dataset_rejects_unknown_tool() -> None:
    data = _dataset()
    case = dict(data["cases"][0])
    expectation = dict(case["expectation"])
    expectation["tool_calls"] = [
        {
            "tool": "drop_database",
            "args": {},
            "requires_confirmation": False,
            "order": 1,
        }
    ]
    case["expectation"] = expectation
    data["cases"] = [case] + list(data["cases"][1:])
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_golden_dataset(data)
    assert any(
        "agent_evals.unknown_tool" in code for code in excinfo.value.error_codes
    )


def test_golden_dataset_rejects_unknown_outcome() -> None:
    data = _dataset()
    case = dict(data["cases"][0])
    expectation = dict(case["expectation"])
    expectation["outcome"] = "exploded"
    case["expectation"] = expectation
    data["cases"] = [case] + list(data["cases"][1:])
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_golden_dataset(data)
    assert any(
        "agent_evals.unknown_outcome" in code for code in excinfo.value.error_codes
    )


def test_golden_dataset_rejects_missing_family_coverage() -> None:
    data = _dataset()
    data["cases"] = [data["cases"][0]]
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_golden_dataset(data)
    assert any(
        "agent_evals.missing_coverage" in code for code in excinfo.value.error_codes
    )


def test_golden_dataset_rejects_incomplete_grounding() -> None:
    data = _dataset()
    case = dict(data["cases"][0])
    expectation = dict(case["expectation"])
    expectation["grounding"] = {
        "require_refs": True,
        "min_refs": 0,
        "declare_missing": False,
    }
    case["expectation"] = expectation
    data["cases"] = [case] + list(data["cases"][1:])
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_golden_dataset(data)
    assert "agent_evals.grounding_min_refs_invalid" in excinfo.value.error_codes
