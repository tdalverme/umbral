# mypy: disable-error-code="arg-type,index,no-untyped-def,no-untyped-call"
from __future__ import annotations

import json
from pathlib import Path

import pytest

from umbral.application.agent_evals.v3.contracts import (
    CaseAggregate,
    CaseDelta,
    ComparisonReport,
    Interval,
    ReviewItem,
    SuiteRun,
    TrialResult,
    TrialTrace,
)
from umbral.application.agent_evals.v3.reporting import (
    render_markdown,
    report_to_dict,
    write_evidence,
)


def _result(case_id: str, trial_index: int, kind: str | None = None) -> TrialResult:
    return TrialResult(
        case_id=case_id,
        trial_index=trial_index,
        attempt_index=0,
        safety_ok=kind != "safety_violation",
        quality_ok=kind is None,
        failure_kind=kind,
        checks=(),
        cost_usd=0.12345,
        trace=TrialTrace(
            case_id=case_id,
            release_id="graph-release-004",
            trial_index=trial_index,
            attempt_index=0,
            turns=(),
            verified_target_ids=frozenset(),
            allowed_ref_ids=frozenset(),
            model_calls=(),
            latency_ms=321,
        ),
    )


def _aggregate(case_id: str, family: str) -> CaseAggregate:
    return CaseAggregate(
        case_id=case_id,
        family=family,
        suite="regression",
        risk="normal",
        successes=1,
        trials=1,
        success_rate=1.0,
        all_trials_succeeded=True,
        interval=Interval(0.7225, 1.0),
        safety_violations=0,
        provider_failures=0,
        product_failures=0,
        average_cost_usd=0.12345,
        average_latency_ms=321,
    )


def _run(release_id: str, *_cases: tuple[str, str]) -> SuiteRun:
    aggregates = [_aggregate(case_id, family) for case_id, family in _cases]
    results = [_result(case_id, 0) for case_id, _family in _cases]
    return SuiteRun(
        dataset_version="conversation-trajectories-v3",
        policy_version="eval-policy-v3",
        release_id=release_id,
        fidelity="managed",
        include_holdout=True,
        complete=True,
        trial_results=tuple(results),
        case_aggregates=tuple(aggregates),
        failures=(),
        total_cost_usd=0.2469,
        total_latency_ms=642,
    )


def _report() -> ComparisonReport:
    baseline = _run(
        "graph-release-003", ("case-a", "family-1"), ("case-b", "family-2")
    )
    candidate = _run(
        "graph-release-004", ("case-a", "family-1"), ("case-b", "family-2")
    )
    return ComparisonReport(
        baseline=baseline,
        candidate=candidate,
        deltas=(
            CaseDelta(
                case_id="case-a",
                baseline_successes=1,
                baseline_trials=1,
                candidate_successes=1,
                candidate_trials=1,
                success_rate_delta=0.0,
                consistency_changed=False,
                cost_delta_usd=0.0,
                latency_delta_ms=0,
                regressed=False,
            ),
        ),
        review_items=(ReviewItem("case-a", "sample", (0,)),),
        blocked=False,
        approvable=True,
        reasons=(),
    )


def test_report_to_dict_contains_verdict_counts_and_review_items() -> None:
    payload = report_to_dict(_report())

    assert payload["verdict"]["approvable"] is True
    assert payload["verdict"]["blocked"] is False
    assert payload["baseline"]["trials"] == 2
    assert payload["candidate"]["trials"] == 2
    assert payload["baseline"]["total_cost_usd"] == 0.2469
    assert payload["baseline"]["total_latency_ms"] == 642
    assert payload["deltas"][0]["success_rate_delta"] == 0.0
    assert payload["review_items"] == [
        {"case_id": "case-a", "reason": "sample", "trial_indexes": [0]}
    ]
    json.dumps(payload, ensure_ascii=False)


def test_rounding_policy_is_applied_in_the_projection() -> None:
    payload = report_to_dict(_report())

    assert payload["baseline"]["total_cost_usd"] == round(0.2469, 4)
    _delta = payload["deltas"][0]
    assert isinstance(_delta["success_rate_delta"], float)
    assert isinstance(_delta["latency_delta_ms"], int)


def test_redaction_masks_sensitive_keys_case_insensitively_and_recursively() -> None:
    from umbral.application.agent_evals.v3.reporting import _redact

    payload = {
        "Api_Key": "sk-123",
        "auth_headers": {"Authorization": "Bearer x", "cookie": "a=b"},
        "nested": {"PASSWORD": "p", "input_tokens": 5},
        "output_tokens": 7,
    }

    redacted = _redact(payload)

    assert redacted["Api_Key"] == "[REDACTED]"
    assert redacted["auth_headers"]["Authorization"] == "[REDACTED]"
    assert redacted["auth_headers"]["cookie"] == "[REDACTED]"
    assert redacted["nested"]["PASSWORD"] == "[REDACTED]"
    assert redacted["nested"]["input_tokens"] == 5
    assert redacted["output_tokens"] == 7


def test_markdown_starts_with_the_verdict_and_detailed_traces_are_bounded() -> None:
    markdown = render_markdown(_report())

    assert markdown.startswith("# Agent Evals v3 — APPROVABLE")
    assert "## Review queue" in markdown
    assert "### case-a (sample)" in markdown
    assert "### case-b" not in markdown
    assert "## Summaries by family / suite / risk" in markdown
    assert "family `family-1`" in markdown


def test_write_evidence_is_atomic_and_well_named(tmp_path: Path) -> None:
    paths = write_evidence(_report(), tmp_path)

    assert paths.json_path.exists()
    assert paths.md_path.exists()
    assert paths.final_dir.name.startswith("graph-release-004-vs-graph-release-003-")
    assert not list(tmp_path.glob(".*.tmp"))
    json.loads(paths.json_path.read_text(encoding="utf-8"))


def test_write_failure_removes_only_the_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_report):
        raise RuntimeError("render failed")

    monkeypatch.setattr(
        "umbral.application.agent_evals.v3.reporting.render_markdown", broken
    )

    with pytest.raises(RuntimeError, match="render failed"):
        write_evidence(_report(), tmp_path)

    assert list(tmp_path.iterdir()) == []