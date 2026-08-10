"""Unit and conformance tests for the strict regression gate."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.matching.policies import baseline_policy, candidate_policy

from umbral.application.matching.contracts import (
    GoldenDataset,
    ReleasesRegistry,
)
from umbral.application.matching.golden import parse_golden_dataset
from umbral.application.matching.regression import run_regression
from umbral.application.matching.releases import parse_releases

ROOT = Path(__file__).resolve().parents[4]
TEST_DATASET_PATH = (
    ROOT / "tests" / "fixtures" / "matching" / "golden-dataset-test.json"
)


def _test_dataset() -> GoldenDataset:
    import json

    raw = json.loads(TEST_DATASET_PATH.read_text(encoding="utf-8"))
    return parse_golden_dataset(raw, require_coverage=False)


def _releases(
    affected: list[str], version: str = "scoring-policy-test-v2"
) -> ReleasesRegistry:
    if not affected:
        return parse_releases(
            {
                "contract_version": "1",
                "registry_version": "matching-releases-v1",
                "releases": [],
            }
        )
    return parse_releases(
        {
            "contract_version": "1",
            "registry_version": "matching-releases-v1",
            "releases": [
                {
                    "id": "rel-test",
                    "artifact": "scoring.policy",
                    "artifact_version": version,
                    "owner": "test-owner",
                    "justification": "pesos ajustados a presupuesto",
                    "affected_case_ids": affected,
                    "date": "2026-08-09",
                }
            ],
        }
    )


def test_same_policy_revision_passes_without_changes() -> None:
    dataset = _test_dataset()
    report = run_regression(
        dataset=dataset,
        baseline_policy=baseline_policy(),
        candidate_policy=baseline_policy(),
        releases=_releases([]),
    )
    assert not report.blocked
    assert report.case_verdicts[0].verdict == "ok"


def test_induced_order_change_blocks_without_release() -> None:
    dataset = _test_dataset()
    report = run_regression(
        dataset=dataset,
        baseline_policy=baseline_policy(),
        candidate_policy=candidate_policy(),
        releases=_releases([]),
    )
    assert report.blocked
    assert report.case_verdicts[0].verdict == "order_change"
    assert any("undeclared_change" in reason for reason in report.reasons)


def test_declared_matching_release_allows_the_change() -> None:
    dataset = _test_dataset()
    report = run_regression(
        dataset=dataset,
        baseline_policy=baseline_policy(),
        candidate_policy=candidate_policy(),
        releases=_releases(["test-001"]),
    )
    assert not report.blocked
    assert report.case_verdicts[0].verdict == "order_change"


def test_release_mismatch_blocks_when_cases_do_not_match() -> None:
    dataset = _test_dataset()
    report = run_regression(
        dataset=dataset,
        baseline_policy=baseline_policy(),
        candidate_policy=candidate_policy(),
        releases=_releases(["other-case"]),
    )
    assert report.blocked
    assert any("release_mismatch" in reason for reason in report.reasons)


def test_gate_failure_raises_regression_blocked_error_type() -> None:
    dataset = _test_dataset()
    report = run_regression(
        dataset=dataset,
        baseline_policy=baseline_policy(),
        candidate_policy=candidate_policy(),
        releases=_releases([]),
    )
    assert report.blocked
    assert isinstance(report.reasons, tuple)
