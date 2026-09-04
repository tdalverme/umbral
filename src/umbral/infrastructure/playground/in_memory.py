"""In-memory adapters used by the local playground only."""

from __future__ import annotations

import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from umbral.application.agent.contracts import GraphRun, ModelCall, NodeRun
from umbral.application.agent.tools.contracts import Proposal
from umbral.application.agent.tools.ports import (
    ProposalDecisionGateway,
    SessionScope,
    SessionScopeReader,
)
from umbral.application.chat.contracts import ChatMessage, ChatSession
from umbral.application.events.contracts import ProductEvent
from umbral.application.radar.contracts import SearchProfile

_NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


class InMemoryChatSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, ChatSession] = {}

    def create(self, session: ChatSession) -> ChatSession:
        self.sessions[session.session_id] = session
        return session

    def get_by_id(self, user_id: UUID, session_id: UUID) -> ChatSession | None:
        session = self.sessions.get(session_id)
        return session if session is not None and session.user_id == user_id else None

    def list_by_user(self, user_id: UUID) -> tuple[ChatSession, ...]:
        return tuple(item for item in self.sessions.values() if item.user_id == user_id)

    def list_by_profile(
        self, user_id: UUID, search_profile_id: UUID
    ) -> tuple[ChatSession, ...]:
        return tuple(
            item
            for item in self.sessions.values()
            if item.user_id == user_id and item.search_profile_id == search_profile_id
        )

    def bind_profile(
        self, session_id: UUID, search_profile_id: UUID
    ) -> ChatSession | None:
        current = self.sessions.get(session_id)
        if current is None:
            return None
        updated = replace(current, search_profile_id=search_profile_id)
        self.sessions[session_id] = updated
        return updated


class InMemoryChatMessageRepository:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def append(self, message: ChatMessage) -> ChatMessage:
        self.messages.append(message)
        return message

    def list_by_session(self, session_id: UUID) -> tuple[ChatMessage, ...]:
        return tuple(item for item in self.messages if item.session_id == session_id)

    def find_by_client_message_id(
        self, session_id: UUID, client_message_id: UUID
    ) -> ChatMessage | None:
        return next(
            (
                item
                for item in self.messages
                if item.session_id == session_id
                and item.client_message_id == client_message_id
            ),
            None,
        )


class FixedProfileStatusReader:
    def status(self, _search_profile_id: UUID) -> str:
        return "active"


class NoopEventWriter:
    def insert(self, _event: ProductEvent) -> None:
        return None


class InMemoryGraphRunRepository:
    _NON_TERMINAL = frozenset({"pending", "running", "interrupted"})

    def __init__(self) -> None:
        self.runs: dict[UUID, GraphRun] = {}

    def create(self, run: GraphRun) -> GraphRun | None:
        if self.active_for_session(run.session_id) is not None:
            return None
        self.runs[run.run_id] = run
        return run

    def get(self, run_id: UUID) -> GraphRun | None:
        return self.runs.get(run_id)

    def active_for_session(self, session_id: UUID) -> GraphRun | None:
        return next(
            (
                run
                for run in self.runs.values()
                if run.session_id == session_id and run.status in self._NON_TERMINAL
            ),
            None,
        )

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
        current = self.runs.get(run_id)
        if current is None:
            return None
        updates = asdict(current)
        if status is not None:
            updates["status"] = status
        if finished_at is not None:
            updates["finished_at"] = finished_at
        if latency_ms is not None:
            updates["latency_ms"] = latency_ms
        if token_usage is not None:
            updates["token_usage"] = dict(token_usage)
        if error_summary is not None:
            updates["error_summary"] = dict(error_summary)
        if attempt is not None:
            updates["attempt"] = attempt
        updated = GraphRun(**updates)
        self.runs[run_id] = updated
        return updated


class PlaygroundTraceCollector:
    """Run recorder that keeps only process-local evidence for the UI."""

    def __init__(self) -> None:
        self.runs: list[GraphRun] = []
        self.nodes: list[NodeRun] = []
        self.calls: list[ModelCall] = []

    def record_graph_run(self, run: GraphRun) -> GraphRun:
        self.runs.append(run)
        return run

    def record_node_run(self, node_run: NodeRun) -> None:
        self.nodes.append(node_run)

    def record_model_call(self, call: ModelCall) -> None:
        self.calls.append(call)


class LocalProposalRepository:
    def __init__(self) -> None:
        self.proposals: dict[UUID, Proposal] = {}

    def insert(self, proposal: Proposal) -> Proposal:
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def enqueue_pending(self, proposal: Proposal) -> Proposal:
        pending = [
            item for item in self.proposals.values()
            if item.search_profile_id == proposal.search_profile_id
            and item.session_id == proposal.session_id
            and item.state == "pending"
        ]
        ordinal = max((item.queue_ordinal for item in pending), default=0) + 1
        for item in pending:
            self.proposals[item.proposal_id] = replace(item, queue_total=ordinal)
        queued = replace(proposal, queue_ordinal=ordinal, queue_total=ordinal)
        self.proposals[queued.proposal_id] = queued
        return queued

    def supersede_and_insert(
        self, proposal_id: UUID, successor: Proposal
    ) -> Proposal | None:
        original = self.proposals.get(proposal_id)
        if original is None or original.state != "pending":
            return None
        self.proposals[proposal_id] = replace(
            original,
            state="rejected",
            rejection_reason="edited",
            superseded_by_proposal_id=successor.proposal_id,
        )
        self.proposals[successor.proposal_id] = successor
        return successor

    def apply_pending(self, proposal_id, applied_idempotency_key, operation):
        current = self.proposals.get(proposal_id)
        if current is None or current.state != "pending":
            return current
        profile_version, run_id = operation(current)
        updated = replace(
            current,
            state="approved",
            applied_idempotency_key=applied_idempotency_key,
            applied_profile_version=profile_version,
            applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def reject_pending(
        self, proposal_id, rejection_reason, rejection_at, rejection_note=None
    ):
        current = self.proposals.get(proposal_id)
        if current is None or current.state != "pending":
            return current
        updated = replace(
            current,
            state="rejected",
            rejection_reason=rejection_reason,
            rejection_note=rejection_note,
        )
        self.proposals[proposal_id] = updated
        return updated

    def get(
        self, proposal_id: UUID, session_id: UUID, user_id: UUID
    ) -> Proposal | None:
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.session_id != session_id:
            return None
        return proposal

    def latest_pending_for_profile(
        self, _search_profile_id: UUID, _session_id: UUID
    ) -> Proposal | None:
        return next(
            (item for item in self.proposals.values() if item.state == "pending"), None
        )

    def pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> tuple[Proposal, ...]:
        return tuple(
            sorted(
                (
                    item for item in self.proposals.values()
                    if item.search_profile_id == search_profile_id
                    and item.session_id == session_id
                    and item.state == "pending"
                ),
                key=lambda item: item.queue_ordinal,
            )
        )

    def list_for_profile(
        self, search_profile_id: UUID, state: str
    ) -> tuple[Proposal, ...]:
        return tuple(
            item
            for item in self.proposals.values()
            if item.search_profile_id == search_profile_id and item.state == state
        )

    def mark_approved(
        self,
        proposal_id: UUID,
        applied_idempotency_key: str,
        *,
        profile_version: int | None = None,
        run_id: UUID | None = None,
    ) -> Proposal | None:
        current = self.proposals.get(proposal_id)
        if current is None:
            return None
        updated = replace(
            current,
            state="approved",
            applied_idempotency_key=applied_idempotency_key,
            applied_profile_version=profile_version,
            applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_rejected(
        self,
        proposal_id: UUID,
        rejection_reason: str,
        _rejection_at: datetime,
        rejection_note: str | None = None,
    ) -> Proposal | None:
        current = self.proposals.get(proposal_id)
        if current is None:
            return None
        updated = replace(
            current,
            state="rejected",
            rejection_reason=rejection_reason,
            rejection_note=rejection_note,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_superseded(
        self,
        proposal_id: UUID,
        superseded_by_proposal_id: UUID,
        _rejection_at: datetime,
    ) -> Proposal | None:
        return self.mark_rejected(
            proposal_id, "edited", _rejection_at
        ) and self._replace_superseded(proposal_id, superseded_by_proposal_id)

    def rebase_pending_for_queue(
        self, search_profile_id: UUID, session_id: UUID, base_profile_version: int
    ) -> None:
        for proposal_id, proposal in tuple(self.proposals.items()):
            if (
                proposal.search_profile_id == search_profile_id
                and proposal.session_id == session_id
                and proposal.state == "pending"
            ):
                self.proposals[proposal_id] = replace(
                    proposal, base_profile_version=base_profile_version
                )

    def _replace_superseded(
        self, proposal_id: UUID, superseded_by_proposal_id: UUID
    ) -> Proposal:
        updated = replace(
            self.proposals[proposal_id],
            superseded_by_proposal_id=superseded_by_proposal_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def expire_pending(self, _expired_before: datetime) -> int:
        return 0


class LocalProfileState:
    """Mutable fixture state owned by one conversation runner instance."""

    def __init__(
        self, profile: Mapping[str, object], listings: tuple[Mapping[str, object], ...]
    ) -> None:
        self.profile = copy.deepcopy(dict(profile))
        self.listings = tuple(copy.deepcopy(dict(item)) for item in listings)

    @property
    def profile_id(self) -> UUID:
        return UUID(str(self.profile["id"]))

    def snapshot(self) -> dict[str, object]:
        return copy.deepcopy(self.profile)

    def as_search_profile(self) -> SearchProfile:
        now = _NOW
        return SearchProfile(
            profile_id=self.profile_id,
            owner_id=UUID(int=1),
            name=str(self.profile.get("name", "Fixture")),
            operation="rental",
            zones=tuple(str(item) for item in self.profile.get("zones", [])),
            budget_max=_number_or_none(self.profile.get("budget_max")),
            budget_min=_number_or_none(self.profile.get("budget_min")),
            min_rooms=_int_or_none(self.profile.get("min_rooms")),
            surface_min=_number_or_none(self.profile.get("surface_min")),
            surface_max=_number_or_none(self.profile.get("surface_max")),
            status="active",
            unknown_strategy={},
            version=int(self.profile.get("version", 1)),
            created_at=now,
            updated_at=now,
            current_version_id=None,
            latest_run_id=None,
            correlation_id=UUID(int=0),
        )

    def validate_change(self, changes: Mapping[str, object]) -> SearchProfile:
        candidate = self.snapshot()
        for key, value in changes.items():
            if key not in {
                "name",
                "zones",
                "budget_max",
                "budget_min",
                "min_rooms",
                "surface_min",
                "surface_max",
            }:
                raise ValueError(f"unsupported profile field: {key}")
            candidate[key] = copy.deepcopy(value)
        budget = candidate.get("budget_max")
        if budget is not None and (not isinstance(budget, (int, float)) or budget <= 0):
            raise ValueError("budget must be positive")
        return replace(self.as_search_profile(), budget_max=_number_or_none(budget))

    def apply(self, changes: Mapping[str, object]) -> SearchProfile:
        self.validate_change(changes)
        self.profile.update(copy.deepcopy(dict(changes)))
        self.profile["version"] = int(self.profile.get("version", 1)) + 1
        return self.as_search_profile()


class LocalRadar:
    def __init__(self, state: LocalProfileState) -> None:
        self.state = state

    def get_profile(self, *, owner_id: UUID, profile_id: UUID) -> SearchProfile:
        self._check(owner_id, profile_id)
        return self.state.as_search_profile()

    def validate_change(
        self, *, owner_id: UUID, profile_id: UUID, changes: Mapping[str, object]
    ) -> SearchProfile:
        self._check(owner_id, profile_id)
        return self.state.validate_change(changes)

    def update_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        changes: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, None]:
        self._check(owner_id, profile_id)
        if int(self.state.profile.get("version", 1)) != expected_version:
            raise ValueError("stale profile")
        return self.state.apply(changes), None

    def _check(self, owner_id: UUID, profile_id: UUID) -> None:
        if owner_id != UUID(int=1) or profile_id != self.state.profile_id:
            raise ValueError("fixture scope mismatch")


class LocalProposalDecisionGateway(ProposalDecisionGateway):
    def __init__(self, proposals: object) -> None:
        self.proposals = proposals

    def get(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
    ) -> Proposal:
        return self.proposals.get(
            user_id=user_id,
            session_id=session_id,
            search_profile_id=search_profile_id,
            proposal_id=proposal_id,
        )

    def reject(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        note: str,
        correlation_id: UUID,
    ) -> Proposal:
        return self.proposals.reject(
            user_id=user_id,
            session_id=session_id,
            search_profile_id=search_profile_id,
            proposal_id=proposal_id,
            note=note,
            correlation_id=correlation_id,
        )

    def derive(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        change: Mapping[str, object],
        correlation_id: UUID,
    ) -> Proposal:
        return self.proposals.derive(
            user_id=user_id,
            session_id=session_id,
            search_profile_id=search_profile_id,
            proposal_id=proposal_id,
            change=change,
            correlation_id=correlation_id,
        )


class LocalScopeReader(SessionScopeReader):
    def __init__(self, profile_id: UUID, session_id: UUID) -> None:
        self.scope = SessionScope(
            session_id=session_id, search_profile_id=profile_id, status="active"
        )

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        return (
            self.scope
            if user_id == UUID(int=1) and session_id == self.scope.session_id
            else None
        )


class NoopPreferenceDecisionGateway:
    def get_proposal(self, **_kwargs: object) -> object:
        raise RuntimeError("preference playground adapter is not configured")

    def confirm_proposal(self, **_kwargs: object) -> object:
        raise RuntimeError("preference playground adapter is not configured")

    def confirm_preference_removal(self, **_kwargs: object) -> object:
        raise RuntimeError("preference playground adapter is not configured")

    def reject_proposal(self, **_kwargs: object) -> object:
        raise RuntimeError("preference playground adapter is not configured")


def _number_or_none(value: object) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
