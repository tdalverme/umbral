"""ConversationTurnService orchestration over fakes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.fakes.conversation import (
    FakeEffectApplier,
    FakeInterpretationGateway,
    FakePendingActionReader,
    FakePendingActionResolver,
    FakeRefreshScheduler,
    FakeTurnContextReader,
)

from umbral.application.conversation.contracts import (
    ConversationAct,
    ConversationTurnContext,
    PendingAction,
    TurnInterpretation,
)
from umbral.application.conversation.service import ConversationTurnService

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _build_service(
    *,
    context: ConversationTurnContext | None = None,
    interpretation: TurnInterpretation | None = None,
    pending: PendingAction | None = None,
) -> tuple[
    ConversationTurnService,
    FakeEffectApplier,
    FakeRefreshScheduler,
    FakePendingActionResolver,
    FakePendingActionReader,
]:
    applier = FakeEffectApplier()
    refresh = FakeRefreshScheduler()
    resolver = FakePendingActionResolver()
    reader = FakePendingActionReader(pending=pending)
    service = ConversationTurnService(
        contexts=FakeTurnContextReader(context=context),
        interpretation=FakeInterpretationGateway(interpretation=interpretation),
        applier=applier,
        pending=reader,
        pending_resolver=resolver,
        refresh=refresh,
        clock=lambda: _NOW,
    )
    return service, applier, refresh, resolver, reader


def _context(*, profile_id: UUID | None = None) -> ConversationTurnContext:
    return ConversationTurnContext(
        user_id=uuid4(),
        session_id=uuid4(),
        verified_profile_id=profile_id,
        radar_filters={},
    )


def test_safe_effects_are_applied_and_refresh_is_scheduled() -> None:
    profile_id = uuid4()
    service, applier, refresh, _resolver, _reader = _build_service(
        context=_context(profile_id=profile_id),
        interpretation=TurnInterpretation(
            acts=(
                ConversationAct(
                    act_id="a1",
                    kind="express_preference",
                    payload={"subject_key": "balcon"},
                ),
            )
        ),
    )

    result = service.process_turn(
        user_id=uuid4(),
        session_id=uuid4(),
        message_text="quiero balcon",
        correlation_id=uuid4(),
    )

    assert [effect.effect_key for effect in result.effects] == [
        "preference.remembered"
    ]
    assert result.routing.refresh_required is True
    assert result.routing.confirmation_required is False
    assert len(refresh.scheduled) == 1
    assert refresh.scheduled[0]["profile_id"] == profile_id
    assert len(applier.applied) == 1


def test_confirmation_required_does_not_schedule_refresh() -> None:
    profile_id = uuid4()
    service, applier, refresh, _resolver, _reader = _build_service(
        context=ConversationTurnContext(
            user_id=uuid4(),
            session_id=uuid4(),
            verified_profile_id=profile_id,
            radar_filters={"budget_max": {"value": 800}},
        ),
        interpretation=TurnInterpretation(
            acts=(
                ConversationAct(
                    act_id="a1",
                    kind="set_filter",
                    payload={"key": "budget_max", "value": 1000},
                ),
            )
        ),
    )

    result = service.process_turn(
        user_id=uuid4(),
        session_id=uuid4(),
        message_text="subo el presupuesto a 1000",
        correlation_id=uuid4(),
    )

    assert result.routing.confirmation_required is True
    assert refresh.scheduled == []
    assert applier.applied == []


def test_pending_effects_are_never_applied_by_the_service() -> None:
    service, applier, _refresh, _resolver, _reader = _build_service(
        context=ConversationTurnContext(
            user_id=uuid4(),
            session_id=uuid4(),
            verified_profile_id=uuid4(),
            radar_filters={"zones": {"zones": ["palermo"]}},
        ),
        interpretation=TurnInterpretation(
            acts=(
                ConversationAct(
                    act_id="a1",
                    kind="clear_filter",
                    payload={"key": "zones"},
                ),
            )
        ),
    )

    result = service.process_turn(
        user_id=uuid4(),
        session_id=uuid4(),
        message_text="sin límite de zona",
        correlation_id=uuid4(),
    )

    assert result.effects[0].status == "pending"
    assert applier.applied == []


def test_resolve_applies_through_the_explicit_resolver() -> None:
    pending = PendingAction(
        kind="profile",
        action_id="proposal-1",
        diff={"budget_max": 1100},
    )
    session_id = uuid4()
    service, _applier, _refresh, resolver, reader = _build_service(
        context=_context(profile_id=uuid4()),
        pending=pending,
    )

    effects = service.resolve(
        user_id=uuid4(),
        session_id=session_id,
        decision={"decision": "approve"},
        correlation_id=uuid4(),
    )

    assert effects[0].effect_key == "pending.resolved"
    assert effects[0].detail["action_id"] == "proposal-1"
    assert resolver.decisions == [
        {"decision": "approve", "action_id": "proposal-1", "kind": "profile"}
    ]


def test_create_radar_when_unbound_applies_without_confirmation() -> None:
    service, applier, refresh, _resolver, _reader = _build_service(
        context=_context(profile_id=None),
        interpretation=TurnInterpretation(
            acts=(ConversationAct(act_id="a1", kind="create_radar"),)
        ),
    )

    result = service.process_turn(
        user_id=uuid4(),
        session_id=uuid4(),
        message_text="quiero un depto luminoso",
        correlation_id=uuid4(),
    )

    assert result.effects[0].effect_key == "radar.created"
    assert result.effects[0].status == "applied"
    assert refresh.scheduled == []  # no durable radar to refresh yet
    assert applier.applied == [result.effects[0]]