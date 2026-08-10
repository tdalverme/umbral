"""Agent ops dashboard service: read-only aggregation (UM-H4-030, R-10)."""

from __future__ import annotations

from umbral.application.agent_ops.contracts import OpsDashboardReport
from umbral.application.agent_ops.ports import OpsRunRepository


class OpsOverviewService:
    """Exposes only read-only aggregates of the agent run registry."""

    def __init__(self, repository: OpsRunRepository) -> None:
        self.repository = repository

    def overview(self) -> OpsDashboardReport:
        return self.repository.overview()
