"""Pure audit report builder for the matching harness.

Reports carry case ids, verdicts, counts and release ids only; 0 listing text,
0 profile text and 0 free-feedback text ever enter a report (FR-011).
"""

from __future__ import annotations

from umbral.application.matching.contracts import (
    FidelityReport,
    RegressionReport,
)


def build_regression_lines(report: RegressionReport) -> tuple[str, ...]:
    """Render the regression report as plain audit lines without PII."""
    lines = [
        f"dataset={report.dataset_version}",
        f"baseline_policy={report.baseline_policy}",
        f"candidate_policy={report.candidate_policy}",
        f"gate={'BLOCKED' if report.blocked else 'PASS'}",
        f"cases={len(report.case_verdicts)}",
    ]
    for verdict in report.case_verdicts:
        lines.append(f"case={verdict.case_id} verdict={verdict.verdict}")
        if verdict.detail:
            lines.append(f"  detail={verdict.detail}")
    for reason in report.reasons:
        lines.append(f"reason={reason}")
    return tuple(lines)


def build_fidelity_lines(report: FidelityReport) -> tuple[str, ...]:
    """Render the fidelity report as plain audit lines without PII."""
    lines = [
        f"fidelity={'PASS' if report.passing else 'FAIL'}",
        f"claims={len(report.claims)}",
    ]
    for claim in report.claims:
        lines.append(f"claim={claim.criterion_key} verdict={claim.verdict}")
    for criterion in report.missing_uncertainty:
        lines.append(f"missing_uncertainty={criterion}")
    for listing_id in report.no_breakdown_items:
        lines.append(f"no_breakdown={listing_id}")
    for reason in report.reasons:
        lines.append(f"reason={reason}")
    return tuple(lines)


def render(reports: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    """Render grouped audit lines; never includes raw product text."""
    blocks: list[str] = []
    for title, lines in reports:
        blocks.append(f"[{title}]")
        blocks.extend(lines)
        blocks.append("")
    return "\n".join(blocks)
