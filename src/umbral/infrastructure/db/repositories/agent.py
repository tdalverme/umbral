"""SQLAlchemy repositories for agent run auditing (H4.1)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from umbral.application.agent.contracts import GraphRun, ModelCall, NodeRun, RunStatus
from umbral.infrastructure.db.models.agent import (
    AgentGraphRun,
    AgentModelCall,
    AgentNodeRun,
)

SessionFactory = Callable[[], Session]

_NON_TERMINAL = ("pending", "running", "interrupted")


class SqlAlchemyGraphRunRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def create(self, run: GraphRun) -> GraphRun | None:
        with self.session_factory() as current:
            current.add(_run_model(run))
            try:
                current.commit()
            except IntegrityError:
                current.rollback()
                return None
        return run

    def get(self, run_id: UUID) -> GraphRun | None:
        with self.session_factory() as current:
            model = current.get(AgentGraphRun, run_id)
            return _to_run(model) if model is not None else None

    def active_for_session(self, session_id: UUID) -> GraphRun | None:
        with self.session_factory() as current:
            model = current.scalar(
                select(AgentGraphRun)
                .where(
                    AgentGraphRun.session_id == session_id,
                    AgentGraphRun.status.in_(_NON_TERMINAL),
                )
                .order_by(AgentGraphRun.created_at.desc())
                .limit(1)
            )
            return _to_run(model) if model is not None else None

    def mark(
        self,
        run_id: UUID,
        *,
        status: str | None = None,
        finished_at: datetime | None = None,
        latency_ms: int | None = None,
        token_usage: Mapping[str, object] | None = None,
        error_summary: Mapping[str, object] | None = None,
        attempt: int | None = None,
    ) -> GraphRun | None:
        with self.session_factory() as current:
            model = current.get(AgentGraphRun, run_id)
            if model is None:
                return None
            if status is not None:
                model.status = status
            if finished_at is not None:
                model.finished_at = finished_at
            if latency_ms is not None:
                model.latency_ms = latency_ms
            if token_usage is not None:
                model.token_usage = dict(token_usage)
            if error_summary is not None:
                model.error_summary = dict(error_summary)
            if attempt is not None:
                model.attempt = attempt
            current.commit()
            return _to_run(model)


class SqlAlchemyNodeRunRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def append(self, node_run: NodeRun) -> None:
        with self.session_factory() as current:
            current.add(
                AgentNodeRun(
                    id=node_run.node_run_id,
                    created_at=node_run.started_at,
                    updated_at=node_run.started_at,
                    actor_kind="service",
                    actor_id=None,
                    source="agent.node",
                    correlation_id=node_run.correlation_id,
                    graph_run_id=node_run.graph_run_id,
                    node_name=node_run.node_name,
                    node_kind=node_run.node_kind,
                    status=node_run.status,
                    started_at=node_run.started_at,
                    finished_at=node_run.finished_at,
                    error_summary=(
                        dict(node_run.error_summary) if node_run.error_summary else None
                    ),
                    usage=dict(node_run.usage) if node_run.usage else None,
                )
            )
            current.commit()


class SqlAlchemyModelCallRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def append(self, call: ModelCall) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as current:
            current.add(
                AgentModelCall(
                    id=call.call_id,
                    created_at=now,
                    updated_at=now,
                    actor_kind="service",
                    actor_id=None,
                    source="agent.model_call",
                    correlation_id=call.correlation_id,
                    graph_run_id=call.graph_run_id,
                    model_version=call.model_version,
                    prompt_version=call.prompt_version,
                    schema_version=call.schema_version,
                    status=call.status,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    total_tokens=call.total_tokens,
                    latency_ms=call.latency_ms,
                    error_code=call.error_code,
                )
            )
            current.commit()


def _run_model(run: GraphRun) -> AgentGraphRun:
    return AgentGraphRun(
        id=run.run_id,
        created_at=run.started_at,
        updated_at=run.started_at,
        actor_kind="service",
        actor_id=None,
        source="agent.graph_run",
        correlation_id=run.correlation_id,
        session_id=run.session_id,
        state_schema_version=run.state_schema_version,
        topology_version=run.topology_version,
        status=run.status,
        attempt=run.attempt,
        started_at=run.started_at,
        finished_at=run.finished_at,
        latency_ms=run.latency_ms,
        error_summary=dict(run.error_summary) if run.error_summary else None,
        token_usage=dict(run.token_usage) if run.token_usage else None,
    )


def _to_run(model: AgentGraphRun) -> GraphRun:
    return GraphRun(
        run_id=model.id,
        session_id=model.session_id,
        state_schema_version=model.state_schema_version,
        topology_version=model.topology_version,
        status=cast(RunStatus, model.status),
        attempt=model.attempt,
        correlation_id=model.correlation_id,
        started_at=model.started_at,
        finished_at=model.finished_at,
        latency_ms=model.latency_ms,
        error_summary=dict(model.error_summary or {}),
        token_usage=dict(model.token_usage or {}),
    )
