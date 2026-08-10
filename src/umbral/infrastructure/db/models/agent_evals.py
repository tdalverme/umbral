"""Auditable eval suites and per-case results for agent evals (H4.4)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

EVAL_GATEWAY_FIDELITY = ENUM(
    "simulated",
    "real",
    name="eval_gateway_fidelity",
    create_type=True,
)
EVAL_SUITE_STATE = ENUM(
    "running",
    "passed",
    "blocked",
    name="eval_suite_state",
    create_type=True,
)
EVAL_CASE_VERDICT = ENUM(
    "ok",
    "tool_selection_change",
    "args_change",
    "grounding_change",
    "confirmation_change",
    "outcome_change",
    "cost_delta",
    "latency_delta",
    name="eval_case_verdict",
    create_type=True,
)


class AgentEvalSuite(IdentityAuditMixin, Base):
    """One eval suite run over the golden dataset under a release."""

    __tablename__ = "agent_eval_suites"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index("ix_agent_eval_suites_created", "created_at"),
        Index("ix_agent_eval_suites_release", "baseline_release_id"),
    )

    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    baseline_release_id: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_release_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    gateway_fidelity: Mapped[str] = mapped_column(
        EVAL_GATEWAY_FIDELITY, nullable=False
    )
    status: Mapped[str] = mapped_column(EVAL_SUITE_STATE, nullable=False)
    blocked_reasons: Mapped[list[object] | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentEvalCaseResult(IdentityAuditMixin, Base):
    """Per-case metrics and verdict of one eval suite."""

    __tablename__ = "agent_eval_case_results"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index("ix_agent_eval_case_results_suite", "eval_suite_id"),
    )

    eval_suite_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_eval_suites.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_selection_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    args_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grounding_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmation_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(EVAL_CASE_VERDICT, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
