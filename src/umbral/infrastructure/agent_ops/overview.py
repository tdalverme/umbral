"""SQLAlchemy aggregation repo for the agent ops dashboard (R-10)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from umbral.application.agent_evals.contracts import ModelCallCostRecord, PriceTable
from umbral.application.agent_evals.price import case_cost
from umbral.application.agent_ops.contracts import (
    EvalRegressionItem,
    OpsDashboardReport,
)
from umbral.infrastructure.db.models.agent import (
    AgentGraphRun,
    AgentModelCall,
    AgentNodeRun,
)
from umbral.infrastructure.db.models.agent_evals import AgentEvalSuite

SessionFactory = Callable[[], Session]

_NON_TERMINAL = ("pending", "running", "interrupted")


class SqlAlchemyOpsRunRepository:
    """Aggregates over the persisted run/eval tables with 0 PII."""

    def __init__(
        self,
        factory: SessionFactory,
        price_table: PriceTable,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.factory = factory
        self.price_table = price_table
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def overview(self) -> OpsDashboardReport:
        with self.factory() as db:
            latencies = db.scalars(
                select(AgentGraphRun.latency_ms).where(
                    AgentGraphRun.status == "completed",
                    AgentGraphRun.latency_ms.isnot(None),
                )
            ).all()
            completed_latencies = [int(item) for item in latencies if item is not None]
            latency_p95 = (
                _p95(sorted(completed_latencies)) if completed_latencies else 0
            )

            total_runs = int(db.scalar(select(func.count(AgentGraphRun.id))) or 0)
            failed_runs = int(
                db.scalar(
                    select(func.count(AgentGraphRun.id)).where(
                        AgentGraphRun.status == "failed"
                    )
                )
                or 0
            )
            interrupted = int(
                db.scalar(
                    select(func.count(AgentGraphRun.id)).where(
                        AgentGraphRun.status == "interrupted"
                    )
                )
                or 0
            )
            error_rate = (
                round((failed_runs + interrupted) / total_runs, 4)
                if total_runs
                else 0.0
            )

            tool_total = int(
                db.scalar(
                    select(func.count(AgentNodeRun.id)).where(
                        AgentNodeRun.node_kind == "tool"
                    )
                )
                or 0
            )
            tool_ok = int(
                db.scalar(
                    select(func.count(AgentNodeRun.id)).where(
                        AgentNodeRun.node_kind == "tool",
                        AgentNodeRun.status == "completed",
                    )
                )
                or 0
            )
            tool_success = round(tool_ok / tool_total, 4) if tool_total else 1.0

            usage_rows = db.execute(
                select(
                    AgentModelCall.model_version,
                    AgentModelCall.input_tokens,
                    AgentModelCall.output_tokens,
                )
            ).all()
            tokens_total = sum(
                int(row[1] or 0) + int(row[2] or 0) for row in usage_rows
            )
            cost_total = round(
                sum(
                    case_cost(
                        [
                            ModelCallCostRecord(
                                model_version=row[0],
                                input_tokens=int(row[1] or 0),
                                output_tokens=int(row[2] or 0),
                            )
                        ],
                        self.price_table,
                    )
                    for row in usage_rows
                ),
                4,
            )

            suite_rows = db.execute(
                select(
                    AgentEvalSuite.id,
                    AgentEvalSuite.candidate_release_id,
                    AgentEvalSuite.status,
                    AgentEvalSuite.blocked_reasons,
                ).where(AgentEvalSuite.status == "blocked")
            ).all()
            regressions = tuple(
                EvalRegressionItem(
                    eval_suite_id=row[0],
                    candidate_release_id=row[1],
                    blocked=True,
                    reasons=tuple(row[3]) if isinstance(row[3], list) else (),
                )
                for row in suite_rows
            )
        return OpsDashboardReport(
            latency_p95_ms=latency_p95,
            error_rate=error_rate,
            tool_success_rate=tool_success,
            interrupt_count=interrupted,
            tokens_total=tokens_total,
            cost_total_usd=cost_total,
            eval_regressions=regressions,
            data_as_of=self.clock(),
        )


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    index = max(0, min(len(values) - 1, int(len(values) * 0.95)))
    return values[index]
