"""Ports for the read-only agent ops dashboard (R-10)."""

from __future__ import annotations

from typing import Protocol

from umbral.application.agent_ops.contracts import OpsDashboardReport


class OpsRunRepository(Protocol):
    """Aggregates the run registry and eval suites for the dashboard."""

    def overview(self) -> OpsDashboardReport: ...
