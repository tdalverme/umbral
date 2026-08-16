"""Infrastructure conversation composition over in-memory fakes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)
from tests.support.radar import RadarTestContext

from umbral.application.chat.service import ChatService
from umbral.application.conversation.contracts import (
    ConversationTurnContext,
    TurnEffect,
)
from umbral.infrastructure.conversation.composition import (
    CopilotServices,
    ProposalsPendingReader,
    ServiceEffectApplier,
    SessionContextReader,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _context(
    *, user_id: UUID, session_id: UUID, profile_id: UUID | None
) -> ConversationTurnContext:
    return ConversationTurnContext(
        user_id=user_id,
        session_id=session_id,
        verified_profile_id=profile_id,
        radar_filters={},
    )


def _chat_service(radar_ctx: RadarTestContext) -> ChatService:
    events = RecordingEventWriter()
    return ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=InMemoryChatMessageRepository(),
        profile_status=FixedProfileStatusReader(),
        events_out=events,
        events_registry=load_events_registry(),
        clock=lambda: _NOW,
    )


def test_service_effect_applier_creates_a_durable_partial_radar() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    applier = ServiceEffectApplier(
        services=CopilotServices(chat=None, radar=radar_ctx.service),  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    effect = TurnEffect(
        effect_key="radar.created",
        act_id="a1",
        status="applied",
    )
    ctx = _context(user_id=user_id, session_id=uuid4(), profile_id=None)

    applied = applier.apply(effect=effect, context=ctx, correlation_id=uuid4())

    assert applied.status == "applied"
    assert applied.object_type == "radar"
    assert applied.object_id is not None
    profile = radar_ctx.service.get_profile(
        owner_id=user_id, profile_id=UUID(applied.object_id)
    )
    assert profile.zones == ()
    assert profile.budget_max is None
    assert profile.min_rooms is None


def test_service_effect_applier_versions_a_filter_change() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=("palermo",),
        budget_max=800.0,
        budget_min=None,
        min_rooms=0,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    applier = ServiceEffectApplier(
        services=CopilotServices(chat=None, radar=radar_ctx.service),  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    effect = TurnEffect(
        effect_key="filter.set",
        act_id="a1",
        status="applied",
        detail={"key": "budget_max", "value": 1000.0},
    )
    ctx = _context(
        user_id=user_id,
        session_id=uuid4(),
        profile_id=profile.profile_id,
    )

    applied = applier.apply(effect=effect, context=ctx, correlation_id=uuid4())

    assert applied.status == "applied"
    updated = radar_ctx.service.get_profile(user_id, profile.profile_id)
    assert updated.budget_max == 1000.0
    assert updated.version == profile.version + 1


def test_service_effect_applier_rejects_filter_without_bound_radar() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    applier = ServiceEffectApplier(
        services=CopilotServices(chat=None, radar=radar_ctx.service),  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    effect = TurnEffect(
        effect_key="filter.set",
        act_id="a1",
        status="applied",
        detail={"key": "budget_max", "value": 1000.0},
    )
    ctx = _context(user_id=uuid4(), session_id=uuid4(), profile_id=None)

    applied = applier.apply(effect=effect, context=ctx, correlation_id=uuid4())

    assert applied.status == "rejected"
    assert applied.reason_code == "radar.not_bound"


def test_session_context_reader_resolves_profile_filters() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=("palermo",),
        budget_max=800.0,
        budget_min=None,
        min_rooms=2,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    chat = _chat_service(radar_ctx)
    session = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    reader = SessionContextReader(
        chat=chat,
        radar=radar_ctx.service,
        pending=ProposalsPendingReader(proposals=None),  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )

    loaded = reader.load(
        user_id=user_id, session_id=session.session_id, correlation_id=uuid4()
    )

    assert loaded.verified_profile_id == profile.profile_id
    assert loaded.profile_name == "Radar"
    assert loaded.radar_filters["zones"]["zones"] == ["palermo"]
    assert loaded.radar_filters["budget_max"]["value"] == 800.0
    assert loaded.radar_filters["min_rooms"]["value"] == 2


def test_unbound_session_resolves_without_a_radar() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    chat = _chat_service(radar_ctx)
    session = chat.create_session(
        user_id=user_id,
        search_profile_id=None,
        correlation_id=uuid4(),
    )
    reader = SessionContextReader(
        chat=chat,
        radar=radar_ctx.service,
        pending=ProposalsPendingReader(proposals=None),  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )

    loaded = reader.load(
        user_id=user_id, session_id=session.session_id, correlation_id=uuid4()
    )

    assert loaded.verified_profile_id is None
    assert loaded.radar_filters == {}
