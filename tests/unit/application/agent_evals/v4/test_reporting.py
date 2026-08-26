from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from umbral.application.agent_evals.v4.contracts import (
    ComparisonEvidenceV4,
    ComparisonTrialV4,
    TrialEvidenceV4,
    TurnEvidenceV4,
)
from umbral.application.agent_evals.v4.grading import grade_trial_v4
from umbral.application.agent_evals.v4.reporting import (
    render_markdown_v4,
    report_to_dict_v4,
)


def comparison_with_api_key(
    api_key: str,
    *,
    policy_input: dict[str, object] | None = None,
) -> ComparisonEvidenceV4:
    turn = TurnEvidenceV4(
        message="recommend a listing",
        authorized_context={"profile": {"Api_Key": api_key}},
        interpretation={"act": "recommend"},
        schema_valid=True,
        policy_input=policy_input or {"listing": {"body": "untrusted listing body"}},
        plan={"action": "reply"},
        effects=(),
        state_before={"recommendations": []},
        state_after={"recommendations": []},
        reply_text="Here is an option.",
        failure_stage="policy_failure",
        reason_codes=("act.untrusted_evidence",),
    )
    evidence = TrialEvidenceV4(
        case_id="case-1",
        release_id="candidate-v5",
        trial_index=3,
        turns=(turn,),
        safety_ok=False,
        quality_ok=True,
        cost_usd=0.01234,
        latency_ms=123,
    )
    trial = ComparisonTrialV4("recommendations", grade_trial_v4(evidence))
    return ComparisonEvidenceV4(baseline=(), candidate=(trial,))


def test_report_contains_representative_stage_evidence_and_redacts_secrets() -> None:
    report = report_to_dict_v4(comparison_with_api_key("secret-value"))
    candidate = cast(dict[str, object], report["candidate"])
    failures = cast(dict[str, int], candidate["failures_by_stage"])
    review_items = cast(list[dict[str, object]], report["review_items"])
    sample = cast(dict[str, object], review_items[0]["sample"])

    assert failures["policy_failure"] == 1
    assert "secret-value" not in json.dumps(report)
    assert sample["reason_codes"] == [
        "act.untrusted_evidence"
    ]


def test_samples_with_the_same_family_stage_and_reason_are_deduplicated() -> None:
    comparison = comparison_with_api_key("secret-value")
    duplicated = ComparisonEvidenceV4(
        baseline=(),
        candidate=comparison.candidate + comparison.candidate,
    )

    report = report_to_dict_v4(duplicated)
    review_items = cast(list[dict[str, object]], report["review_items"])

    assert len(review_items) == 1


def test_markdown_is_deterministic_and_omits_untrusted_listing_bodies() -> None:
    comparison = comparison_with_api_key("secret-value")

    first = render_markdown_v4(comparison)
    second = render_markdown_v4(comparison)

    assert first == second
    assert "secret-value" not in first
    assert "untrusted listing body" not in first


def test_neutral_and_nested_fields_cannot_emit_untrusted_listing_bodies() -> None:
    untrusted_body = "untrusted listing body " * 100
    comparison = comparison_with_api_key(
        "secret-value",
        policy_input={
            "selected": {"description": untrusted_body},
            "payload": untrusted_body,
            "description": untrusted_body,
        },
    )

    report = report_to_dict_v4(comparison)
    markdown = render_markdown_v4(comparison)

    assert untrusted_body not in json.dumps(report)
    assert untrusted_body not in markdown


def test_diagnostic_field_values_cannot_emit_untrusted_listing_bodies() -> None:
    untrusted_body = "untrusted listing body " * 5
    comparison = comparison_with_api_key(
        "secret-value",
        policy_input={"status": untrusted_body},
    )

    report = report_to_dict_v4(comparison)
    markdown = render_markdown_v4(comparison)

    assert untrusted_body not in json.dumps(report)
    assert untrusted_body not in markdown


def test_dynamic_field_names_cannot_emit_untrusted_listing_bodies() -> None:
    untrusted_body = "untrusted listing body " * 5
    comparison = comparison_with_api_key(
        "secret-value",
        policy_input={untrusted_body: "value"},
    )

    report = report_to_dict_v4(comparison)
    markdown = render_markdown_v4(comparison)

    assert untrusted_body not in json.dumps(report)
    assert untrusted_body not in markdown


def test_every_emitted_string_has_a_deterministic_hard_maximum() -> None:
    long_value = "x" * 257
    comparison = comparison_with_api_key("secret-value")
    original = comparison.candidate[0]
    turn = replace(original.result.evidence.turns[0], reason_codes=(long_value,))
    evidence = replace(original.result.evidence, turns=(turn,))
    candidate = ComparisonTrialV4(original.family, grade_trial_v4(evidence))
    report = report_to_dict_v4(ComparisonEvidenceV4((), (candidate,)))

    assert long_value not in json.dumps(report)
    assert all(len(value) <= 256 for value in _strings_in(report))


def _strings_in(value: object) -> list[str]:
    if isinstance(value, dict):
        return [
            *[str(key) for key in value],
            *[item for nested in value.values() for item in _strings_in(nested)],
        ]
    if isinstance(value, list):
        return [item for nested in value for item in _strings_in(nested)]
    return [value] if isinstance(value, str) else []
