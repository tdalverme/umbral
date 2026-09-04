"""Unit tests for V5 radar command execution over real services."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)
from tests.support.radar import RadarTestContext

from umbral.application.agent.tools.contracts import Proposal
from umbral.application.agent.tools.ports import ProposalRepository
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.conversation.v5.contracts import (
    ClearFilterCommand,
    CreateRadarCommand,
    HardFilterV5,
    PendingActionV5,
    SetFilterCommand,
    TurnContextV5,
)
from umbral.application.events.contracts import ProductEvent
from umbral.infrastructure.conversation.v5.executor import (
    EffectExecutorV5,
    ProposalsPendingResolverV5,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


class _ProposalRepo:
    def __init__(self) -> None:
        self.proposals: dict[UUID, Proposal] = {}

    def insert(self, proposal: Proposal) -> Proposal:
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def get(
        self, proposal_id: UUID, session_id: UUID, user_id: UUID
    ) -> Proposal | None:
        return self.proposals.get(proposal_id)

    def latest_pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> Proposal | None:
        return None

    def pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> tuple[Proposal, ...]:
        return tuple(
            item for item in self.proposals.values()
            if item.search_profile_id == search_profile_id
            and item.session_id == session_id
            and item.state == "pending"
        )

    def mark_approved(
        self,
        proposal_id: UUID,
        key: str,
        *,
        profile_version: int | None = None,
        run_id: UUID | None = None,
    ) -> Proposal | None:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        updated = replace(
            proposal,
            state="approved",
            applied_idempotency_key=key,
            applied_profile_version=profile_version,
            applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_rejected(
        self,
        proposal_id: UUID,
        reason: str,
        rejection_at: datetime,
        rejection_note: str | None = None,
    ) -> Proposal | None:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason=reason,  # type: ignore[arg-type]
            rejection_note=rejection_note,
        )
        self.proposals[proposal_id] = updated
        return updated

    def expire_pending(self, expired_before: datetime) -> int:
        return 0


class _Events:
    def __init__(self) -> None:
        self.events: list[ProductEvent] = []

    def insert(self, event: ProductEvent) -> None:
        self.events.append(event)


def _proposals(radar_ctx: RadarTestContext) -> SearchProfileUpdateProposals:
    return SearchProfileUpdateProposals(
        repository=cast(ProposalRepository, _ProposalRepo()),
        radar=radar_ctx.service,
        events=_Events(),
        events_registry=load_events_registry(),
        ttl_hours=24,
        clock=lambda: _NOW,
    )


def _chat_service() -> ChatService:
    return ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=InMemoryChatMessageRepository(),
        profile_status=FixedProfileStatusReader(),
        events_out=RecordingEventWriter(),
        events_registry=load_events_registry(),
        clock=lambda: _NOW,
    )


def _context(
    *,
    profile_id: UUID,
    version: int,
    filters: tuple[HardFilterV5, ...],
    user_id: UUID,
    session_id: UUID,
) -> TurnContextV5:
    return TurnContextV5(
        user_id=str(user_id),
        session_id=str(session_id),
        active_radar_ref=f"radar:{profile_id}",
        active_radar_version=version,
        current_filters=filters,
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=(
            "create_radar",
            "set_filter",
            "clear_filter",
            "query",
        ),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=str(uuid4()),
    )


def _executor(
    radar_ctx: RadarTestContext, chat: ChatService
) -> EffectExecutorV5:
    return EffectExecutorV5(
        radar=radar_ctx.service,
        chat=chat,
        proposals=_proposals(radar_ctx),
    )


def test_create_radar_binds_session_and_is_idempotent() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    chat = _chat_service()
    session = chat.create_session(
        user_id=user_id, search_profile_id=None, correlation_id=uuid4()
    )
    executor = _executor(radar_ctx, chat)
    context = _context(
        profile_id=uuid4(),
        version=0,
        filters=(),
        user_id=user_id,
        session_id=session.session_id,
    )
    context = replace(context, active_radar_ref=None, active_radar_version=None)
    command = CreateRadarCommand(act_id="a1", name="Mi búsqueda")

    first = executor.execute(
        command=command, context=context, idempotency_key="turn:a0"
    )
    second = executor.execute(
        command=command, context=context, idempotency_key="turn:a0"
    )

    assert first.object_ref == second.object_ref
    assert first.effect_key == "radar.created"
    assert len(radar_ctx.service.list_profiles(user_id, None)) == 1
    bound = chat.get_session(user_id=user_id, session_id=session.session_id)
    assert bound.search_profile_id is not None
    assert first.object_ref == f"radar:{bound.search_profile_id}"


def test_new_filter_creates_pending_proposal_without_versioning_the_radar() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    chat = _chat_service()
    executor = _executor(radar_ctx, chat)
    context = _context(
        profile_id=profile.profile_id,
        version=profile.version,
        filters=(),
        user_id=user_id,
        session_id=uuid4(),
    )

    result = executor.execute(
        command=SetFilterCommand(
            act_id="a1",
            filter_key="budget_max",
            value=900,
            expected_profile_version=profile.version,
        ),
        context=context,
        idempotency_key="turn:a1",
    )

    assert result.effect_key == "filter.set"
    assert result.object_ref is not None
    assert result.object_ref.startswith("proposal:")
    assert result.reason_code == "filter.requires_confirmation"
    updated = radar_ctx.service.get_profile(user_id, profile.profile_id)
    assert updated.budget_max is None


def test_rejecting_pending_returns_a_rejected_resolution_outcome() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    chat = _chat_service()
    session = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    proposals = _proposals(radar_ctx)
    proposal = proposals.propose(
        user_id=user_id,
        session_id=session.session_id,
        search_profile_id=profile.profile_id,
        change={"budget_max": 900},
        correlation_id=uuid4(),
    )
    context = _context(
        profile_id=profile.profile_id,
        version=profile.version,
        filters=(),
        user_id=user_id,
        session_id=session.session_id,
    )
    context = replace(
        context,
        pending_action=PendingActionV5(pending_ref=f"pending:{proposal.proposal_id}"),
    )

    result = ProposalsPendingResolverV5(proposals=proposals).resolve(
        act_id="resolve:a1",
        context=context,
        pending_ref=f"pending:{proposal.proposal_id}",
        decision="reject",
        correlation_id=uuid4(),
        idempotency_key="decision:a1",
    )

    assert result.status == "rejected"
    assert result.reason_code == "user"


def test_existing_filter_change_creates_pending_proposal() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=(),
        budget_max=800.0,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    chat = _chat_service()
    executor = _executor(radar_ctx, chat)
    context = _context(
        profile_id=profile.profile_id,
        version=profile.version,
        filters=(HardFilterV5(filter_key="budget_max", value=800.0),),
        user_id=user_id,
        session_id=uuid4(),
    )

    result = executor.execute(
        command=SetFilterCommand(
            act_id="a1",
            filter_key="budget_max",
            value=1200,
            expected_profile_version=profile.version,
        ),
        context=context,
        idempotency_key="turn:a1",
    )

    assert result.effect_key == "filter.set"
    assert result.object_ref is not None
    assert result.object_ref.startswith("proposal:")
    assert result.reason_code == "filter.requires_confirmation"
    updated = radar_ctx.service.get_profile(user_id, profile.profile_id)
    assert updated.budget_max == 800.0


def test_clear_filter_creates_pending_proposal_and_keeps_state() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=("palermo",),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    chat = _chat_service()
    executor = _executor(radar_ctx, chat)
    context = _context(
        profile_id=profile.profile_id,
        version=profile.version,
        filters=(HardFilterV5(filter_key="zones", value=("palermo",)),),
        user_id=user_id,
        session_id=uuid4(),
    )

    result = executor.execute(
        command=ClearFilterCommand(
            act_id="a1",
            filter_key="zones",
            expected_profile_version=profile.version,
        ),
        context=context,
        idempotency_key="turn:a1",
    )

    assert result.effect_key == "filter.cleared"
    assert result.object_ref is not None
    assert result.object_ref.startswith("proposal:")
    assert result.reason_code == "filter.requires_confirmation"
    updated = radar_ctx.service.get_profile(user_id, profile.profile_id)
    assert updated.zones == ("palermo",)


def test_hard_filter_proposal_does_not_mutate_a_stale_radar() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    radar_ctx.service.version_profile(
        owner_id=user_id,
        profile_id=profile.profile_id,
        expected_version=profile.version,
        changes={"budget_max": 700.0},
        correlation_id=uuid4(),
    )
    chat = _chat_service()
    executor = _executor(radar_ctx, chat)
    context = _context(
        profile_id=profile.profile_id,
        version=profile.version,
        filters=(),
        user_id=user_id,
        session_id=uuid4(),
    )

    result = executor.execute(
        command=SetFilterCommand(
            act_id="a1",
            filter_key="min_rooms",
            value=2,
            expected_profile_version=profile.version,
        ),
        context=context,
        idempotency_key="turn:a1",
    )

    assert result.effect_key == "filter.set"
    assert result.object_ref is not None
    assert result.object_ref.startswith("proposal:")
    assert result.reason_code == "filter.requires_confirmation"
