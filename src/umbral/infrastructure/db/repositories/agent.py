"""SQLAlchemy repositories for agent run auditing and proposals (H4.1/H4.2)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from umbral.application.agent.contracts import GraphRun, ModelCall, NodeRun, RunStatus
from umbral.application.agent.tools.contracts import (
    Proposal,
    ProposalRejectionReason,
    ProposalState,
)
from umbral.infrastructure.db.models.agent import (
    AgentGraphRun,
    AgentModelCall,
    AgentNodeRun,
    SearchProfileUpdateProposal,
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
        release_id=run.release_id,
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
        release_id=model.release_id,
    )


class SqlAlchemyProposalRepository:
    """Scoped persistence for durable proposals (FR-008, R-03)."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, proposal: Proposal) -> Proposal:
        with self.session_factory() as current:
            current.add(_proposal_model(proposal))
            current.commit()
        return proposal

    def get(
        self, proposal_id: UUID, session_id: UUID, user_id: UUID
    ) -> Proposal | None:
        with self.session_factory() as current:
            model = current.scalar(
                select(SearchProfileUpdateProposal).where(
                    SearchProfileUpdateProposal.id == proposal_id,
                    SearchProfileUpdateProposal.session_id == session_id,
                )
            )
            return _to_proposal(model) if model is not None else None

    def latest_pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> Proposal | None:
        with self.session_factory() as current:
            model = current.scalar(
                select(SearchProfileUpdateProposal)
                .where(
                    SearchProfileUpdateProposal.search_profile_id
                    == search_profile_id,
                    SearchProfileUpdateProposal.session_id == session_id,
                    SearchProfileUpdateProposal.state == "pending",
                )
                .order_by(SearchProfileUpdateProposal.created_at.desc())
                .limit(1)
            )
            return _to_proposal(model) if model is not None else None

    def list_for_profile(
        self,
        search_profile_id: UUID,
        state: str,
    ) -> tuple[Proposal, ...]:
        with self.session_factory() as current:
            models = current.scalars(
                select(SearchProfileUpdateProposal)
                .where(
                    SearchProfileUpdateProposal.search_profile_id
                    == search_profile_id,
                    SearchProfileUpdateProposal.state == state,
                )
                .order_by(SearchProfileUpdateProposal.created_at.desc())
            )
            return tuple(_to_proposal(model) for model in models)

    def mark_approved(
        self,
        proposal_id: UUID,
        applied_idempotency_key: str,
        *,
        profile_version: int | None = None,
        run_id: UUID | None = None,
    ) -> Proposal | None:
        with self.session_factory() as current:
            model = current.get(SearchProfileUpdateProposal, proposal_id)
            if model is None:
                return None
            model.state = "approved"
            model.applied_idempotency_key = applied_idempotency_key
            model.rejection_reason = None
            model.applied_profile_version = profile_version
            model.applied_run_id = run_id
            model.updated_at = datetime.now(timezone.utc)
            current.commit()
            return _to_proposal(model)

    def mark_rejected(
        self,
        proposal_id: UUID,
        rejection_reason: str,
        rejection_at: datetime,
        rejection_note: str | None = None,
    ) -> Proposal | None:
        with self.session_factory() as current:
            model = current.get(SearchProfileUpdateProposal, proposal_id)
            if model is None:
                return None
            model.state = "rejected"
            model.rejection_reason = rejection_reason
            model.rejection_note = rejection_note
            model.updated_at = rejection_at
            current.commit()
            return _to_proposal(model)

    def mark_superseded(
        self,
        proposal_id: UUID,
        superseded_by_proposal_id: UUID,
        rejection_at: datetime,
    ) -> Proposal | None:
        with self.session_factory() as current:
            model = current.get(SearchProfileUpdateProposal, proposal_id)
            if model is None:
                return None
            model.state = "rejected"
            model.rejection_reason = "edited"
            model.superseded_by_proposal_id = superseded_by_proposal_id
            model.updated_at = rejection_at
            current.commit()
            return _to_proposal(model)

    def expire_pending(self, expired_before: datetime) -> int:
        with self.session_factory() as current:
            result = current.execute(
                update(SearchProfileUpdateProposal)
                .where(
                    SearchProfileUpdateProposal.state == "pending",
                    SearchProfileUpdateProposal.expires_at < expired_before,
                )
                .values(
                    state="rejected",
                    rejection_reason="expired",
                    updated_at=datetime.now(timezone.utc),
                )
            )
            current.commit()
            return int(result.rowcount or 0)  # type: ignore[attr-defined]


def _proposal_model(proposal: Proposal) -> SearchProfileUpdateProposal:
    now = proposal.expires_at
    return SearchProfileUpdateProposal(
        id=proposal.proposal_id,
        created_at=now,
        updated_at=now,
        actor_kind="service",
        actor_id=str(proposal.session_id),
        source="agent.tool",
        correlation_id=proposal.correlation_id or proposal.proposal_id,
        session_id=proposal.session_id,
        search_profile_id=proposal.search_profile_id,
        base_profile_version=proposal.base_profile_version,
        diff=dict(proposal.diff),
        impact=dict(proposal.impact),
        state=proposal.state,
        expires_at=proposal.expires_at,
        applied_idempotency_key=proposal.applied_idempotency_key,
        rejection_reason=proposal.rejection_reason,
        applied_profile_version=proposal.applied_profile_version,
        applied_run_id=proposal.applied_run_id,
        rejection_note=proposal.rejection_note,
        superseded_by_proposal_id=proposal.superseded_by_proposal_id,
    )


def _to_proposal(model: SearchProfileUpdateProposal) -> Proposal:
    return Proposal(
        proposal_id=model.id,
        session_id=model.session_id,
        search_profile_id=model.search_profile_id,
        base_profile_version=model.base_profile_version,
        diff=dict(model.diff or {}),
        impact=dict(model.impact or {}),
        state=cast(ProposalState, model.state),
        expires_at=model.expires_at,
        applied_idempotency_key=model.applied_idempotency_key,
        rejection_reason=cast(ProposalRejectionReason | None, model.rejection_reason),
        applied_profile_version=model.applied_profile_version,
        applied_run_id=model.applied_run_id,
        correlation_id=model.correlation_id,
        rejection_note=model.rejection_note,
        superseded_by_proposal_id=model.superseded_by_proposal_id,
    )
