"""SQLAlchemy persistence of eval suites and per-case results (R-08)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from umbral.application.agent_evals.contracts import CaseEvalResult, EvalSuiteReport
from umbral.infrastructure.db.models.agent_evals import (
    AgentEvalCaseResult,
    AgentEvalSuite,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyEvalSuiteRepository:
    """Persists eval suites and per-case results with 0 PII."""

    def __init__(self, factory: SessionFactory) -> None:
        self.factory = factory

    def create_suite(
        self,
        *,
        report: EvalSuiteReport,
        started_at: datetime,
        finished_at: datetime,
    ) -> UUID:
        suite_id = uuid4()
        with self.factory() as db:
            db.add(
                AgentEvalSuite(
                    id=suite_id,
                    dataset_version=report.dataset_version,
                    baseline_release_id=report.baseline_release_id,
                    candidate_release_id=report.candidate_release_id,
                    gateway_fidelity=report.gateway_fidelity,
                    status="blocked" if report.blocked else "passed",
                    blocked_reasons=list(report.reasons) if report.reasons else None,
                    metrics=dict(report.metrics),
                    started_at=started_at,
                    finished_at=finished_at,
                    created_at=started_at,
                    updated_at=finished_at,
                    source="agent_evals",
                    correlation_id=uuid4(),
                )
            )
            db.commit()
        return suite_id

    def append_case_result(self, *, suite_id: UUID, result: CaseEvalResult) -> None:
        now = datetime.now()
        with self.factory() as db:
            db.add(
                AgentEvalCaseResult(
                    eval_suite_id=suite_id,
                    case_id=result.case_id,
                    tool_selection_ok=result.tool_selection_ok,
                    args_valid=result.args_valid,
                    grounding_ok=result.grounding_ok,
                    confirmation_ok=result.confirmation_ok,
                    outcome_ok=result.outcome_ok,
                    cost_usd=result.cost_usd,
                    latency_ms=result.latency_ms,
                    verdict=result.verdict,
                    reason=result.reason or None,
                    created_at=now,
                    updated_at=now,
                    source="agent_evals",
                    correlation_id=uuid4(),
                )
            )
            db.commit()
