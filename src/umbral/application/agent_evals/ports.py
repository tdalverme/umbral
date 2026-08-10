"""Ports for persisting eval suites (research R-08)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.agent_evals.contracts import (
    CaseEvalResult,
    EvalSuiteReport,
)


class EvalSuiteRepository(Protocol):
    """Persists an eval suite and its per-case results (0 PII, R-08)."""

    def create_suite(
        self,
        *,
        report: EvalSuiteReport,
        started_at: datetime,
        finished_at: datetime,
    ) -> UUID: ...

    def append_case_result(self, *, suite_id: UUID, result: CaseEvalResult) -> None: ...
