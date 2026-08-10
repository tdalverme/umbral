"""Unit tests of the agent ops overview service (T038)."""

from __future__ import annotations

from datetime import datetime, timezone

from umbral.application.agent_ops.contracts import OpsDashboardReport
from umbral.application.agent_ops.service import OpsOverviewService


class _FakeRepo:
    def __init__(self, report: OpsDashboardReport) -> None:
        self.report = report

    def overview(self) -> OpsDashboardReport:
        return self.report


def test_service_returns_the_repository_aggregates() -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    report = OpsDashboardReport(
        latency_p95_ms=1200,
        error_rate=0.02,
        tool_success_rate=0.98,
        interrupt_count=3,
        tokens_total=120000,
        cost_total_usd=0.25,
        eval_regressions=(),
        data_as_of=now,
    )
    service = OpsOverviewService(_FakeRepo(report))
    assert service.overview() is report
