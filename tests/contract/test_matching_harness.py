"""Harness-level conformance: reports without PII and no new product surfaces."""

from __future__ import annotations

from pathlib import Path

from umbral.application.matching.contracts import FidelityReport, RegressionReport
from umbral.application.matching.golden import load_golden_dataset
from umbral.application.matching.report import (
    build_fidelity_lines,
    build_regression_lines,
    render,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "matching" / "v1" / "golden-dataset-v1.json"


def test_report_lines_never_contain_listing_or_profile_text() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    case_text = {case.notes for case in dataset.cases if case.notes}
    listing_text = {
        listing.neighborhood or ""
        for case in dataset.cases
        for listing in case.listings
    }
    profile_zones = {zone for case in dataset.cases for zone in case.profile.zones}
    forbidden = {str(item) for item in (*case_text, *listing_text, *profile_zones)}
    forbidden.discard("")

    lines = build_regression_lines(_sample_regression_report()) + build_fidelity_lines(
        _sample_fidelity_report()
    )
    for line in lines:
        for token in forbidden:
            assert token not in line, f"report leaked product text: {token}"


def test_render_groups_reports_without_pii() -> None:
    text = render(
        (
            ("regression", build_regression_lines(_sample_regression_report())),
            ("fidelity", build_fidelity_lines(_sample_fidelity_report())),
        )
    )
    assert "[regression]" in text
    assert "[fidelity]" in text
    assert "listing_text_placeholder" not in text


def _sample_regression_report() -> RegressionReport:
    from umbral.application.matching.contracts import CaseVerdictItem

    return RegressionReport(
        dataset_version="golden-dataset-v1",
        baseline_policy="scoring-policy-v1",
        candidate_policy="scoring-policy-v1",
        case_verdicts=(CaseVerdictItem(case_id="golden-001", verdict="ok", detail=""),),
        blocked=False,
        reasons=(),
    )


def _sample_fidelity_report() -> FidelityReport:
    from umbral.application.matching.contracts import ClaimVerdictItem

    return FidelityReport(
        passing=True,
        claims=(
            ClaimVerdictItem(
                criterion_key="presupuesto", verdict="supported", detail="evidence_ref"
            ),
        ),
        missing_uncertainty=(),
        no_breakdown_items=(),
        reasons=(),
    )
