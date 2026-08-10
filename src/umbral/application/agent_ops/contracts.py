"""Read-only agent ops dashboard values (UM-H4-030, R-10)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EvalRegressionItem:
    """One eval suite surfaced by the dashboard (linked to its release)."""

    eval_suite_id: UUID
    candidate_release_id: str | None
    blocked: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OpsDashboardReport:
    """Read-only aggregates over the run registry; 0 PII (FR-017..FR-019)."""

    latency_p95_ms: int
    error_rate: float
    tool_success_rate: float
    interrupt_count: int
    tokens_total: int
    cost_total_usd: float
    eval_regressions: tuple[EvalRegressionItem, ...]
    data_as_of: datetime
    metrics: Mapping[str, float] | None = None
