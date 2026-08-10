"""Budget consumption source and gate over persisted run records (R-09)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from umbral.application.agent.budgets import (
    BudgetConsumption,
    BudgetPolicy,
    evaluate_budget,
)
from umbral.application.agent.contracts import BudgetVerdict
from umbral.application.agent_evals.contracts import (
    ModelCallCostRecord,
    PriceTable,
)
from umbral.application.agent_evals.price import case_cost
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.models.agent import (
    AgentGraphRun,
    AgentModelCall,
    AgentNodeRun,
)
from umbral.infrastructure.db.models.chat import ChatSession

SessionFactory = Callable[[], Session]

_NON_TERMINAL = ("pending", "running", "interrupted")


class SqlAlchemyBudgetConsumptionSource:
    """Computes consumption from the persisted run audit tables."""

    def __init__(self, factory: SessionFactory, price_table: PriceTable) -> None:
        self.factory = factory
        self.price_table = price_table

    def consumption(
        self, *, user_id: UUID, session_id: UUID, since: object
    ) -> BudgetConsumption:
        since_dt = since if isinstance(since, datetime) else datetime.now(timezone.utc)
        with self.factory() as db:
            session_run_ids = db.scalars(
                select(AgentGraphRun.id).where(
                    AgentGraphRun.session_id == session_id,
                    AgentGraphRun.created_at >= since_dt,
                )
            ).all()
            user_run_ids = db.scalars(
                select(AgentGraphRun.id)
                .join(ChatSession, ChatSession.id == AgentGraphRun.session_id)
                .where(
                    ChatSession.user_id == user_id,
                    AgentGraphRun.created_at >= since_dt,
                )
            ).all()

            session_tokens = 0
            session_cost = 0.0
            user_tokens = 0
            user_cost = 0.0
            if user_run_ids:
                rows = db.execute(
                    select(
                        AgentModelCall.graph_run_id,
                        AgentModelCall.model_version,
                        AgentModelCall.input_tokens,
                        AgentModelCall.output_tokens,
                    ).where(AgentModelCall.graph_run_id.in_(user_run_ids))
                ).all()
                session_run_set = set(session_run_ids)
                for row in rows:
                    tokens = int(row[2] or 0) + int(row[3] or 0)
                    user_tokens += tokens
                    cost = case_cost(
                        [
                            ModelCallCostRecord(
                                model_version=row[1],
                                input_tokens=int(row[2] or 0),
                                output_tokens=int(row[3] or 0),
                            )
                        ],
                        self.price_table,
                    )
                    user_cost += cost
                    if row[0] in session_run_set:
                        session_tokens += tokens
                        session_cost += cost

            session_tool_calls = 0
            if session_run_ids:
                session_tool_calls = int(
                    db.scalar(
                        select(func.count(AgentNodeRun.id)).where(
                            AgentNodeRun.graph_run_id.in_(session_run_ids),
                            AgentNodeRun.node_kind == "tool",
                        )
                    )
                    or 0
                )

            active_user_runs = int(
                db.scalar(
                    select(func.count(AgentGraphRun.id))
                    .join(ChatSession, ChatSession.id == AgentGraphRun.session_id)
                    .where(
                        ChatSession.user_id == user_id,
                        AgentGraphRun.status.in_(_NON_TERMINAL),
                    )
                )
                or 0
            )
        return BudgetConsumption(
            session_tokens=session_tokens,
            user_tokens=user_tokens,
            session_tool_calls=session_tool_calls,
            user_cost_usd=round(user_cost, 4),
            active_user_runs=active_user_runs,
        )


class SettingsBudgetGate:
    """Evaluates the budget before a run from settings-derived policy."""

    def __init__(
        self,
        *,
        source: SqlAlchemyBudgetConsumptionSource,
        policy: BudgetPolicy,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.source = source
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def check(self, *, user_id: UUID, session_id: UUID) -> BudgetVerdict:
        since = self.clock() - timedelta(hours=self.policy.window_hours)
        consumption = self.source.consumption(
            user_id=user_id, session_id=session_id, since=since
        )
        return evaluate_budget(policy=self.policy, consumption=consumption)


def policy_from_settings(settings: Settings) -> BudgetPolicy:
    return BudgetPolicy(
        window_hours=settings.agent_budget_window_hours,
        session_token_cap=settings.agent_budget_session_token_cap,
        user_token_cap=settings.agent_budget_user_token_cap,
        session_tool_call_cap=settings.agent_budget_session_tool_call_cap,
        user_cost_cap_usd=settings.agent_budget_user_cost_cap_usd,
        user_concurrency_cap=settings.agent_budget_user_concurrency_cap,
        warning_ratio=settings.agent_budget_warning_ratio,
    )
