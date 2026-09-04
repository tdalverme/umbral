"""Unit tests for V5 contextual feedback execution."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from uuid import UUID, uuid4

from tests.support.radar import RadarTestContext

from umbral.application.conversation.contracts import (
    RecordFeedbackCommand,
    TurnContext,
)
from umbral.infrastructure.conversation.executor import EffectExecutor


class _FakeFeedback:
    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []

    def record_feedback(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_id: UUID,
        run_id: UUID | None,
        event_type: str,
        reason_keys: tuple[str, ...],
        idempotency_key: str,
        correlation_id: UUID,
        concept_feedback: tuple[Mapping[str, object], ...] = (),
        free_feedback: str | None = None,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object:
        self.calls.append(
            SimpleNamespace(
                owner_id=owner_id,
                profile_id=profile_id,
                listing_id=listing_id,
                event_type=event_type,
                idempotency_key=idempotency_key,
                free_feedback=free_feedback,
            )
        )
        return object()


def _context(*, profile_id: UUID, user_id: UUID, session_id: UUID) -> TurnContext:
    return TurnContext(
        user_id=str(user_id),
        session_id=str(session_id),
        active_radar_ref=f"radar:{profile_id}",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=("record_feedback", "query"),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=str(uuid4()),
    )


def test_feedback_records_through_the_feedback_seam() -> None:
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
    feedback = _FakeFeedback()
    executor = EffectExecutor(
        radar=radar_ctx.service,
        chat=None,  # type: ignore[arg-type]
        proposals=None,  # type: ignore[arg-type]
        feedback=feedback,
    )
    context = _context(
        profile_id=profile.profile_id, user_id=user_id, session_id=uuid4()
    )
    listing_id = uuid4()

    result = executor.execute(
        command=RecordFeedbackCommand(
            act_id="a1",
            listing_id=listing_id,
            feedback_type="dislike",
            raw_text="No me gusta",
        ),
        context=context,
        idempotency_key="conversation:session:message:a1",
    )

    assert result.status == "applied"
    assert result.effect_key == "feedback.recorded"
    assert result.object_ref == f"listing:{listing_id}"
    assert len(feedback.calls) == 1
    call = feedback.calls[0]
    assert call.listing_id == listing_id
    assert call.profile_id == profile.profile_id
    assert call.event_type == "dislike"
    assert call.idempotency_key == "conversation:session:message:a1"
    assert call.free_feedback == "No me gusta"


def test_feedback_without_bound_radar_is_rejected() -> None:
    executor = EffectExecutor(
        radar=RadarTestContext(default_runtime=False).service,
        chat=None,  # type: ignore[arg-type]
        proposals=None,  # type: ignore[arg-type]
        feedback=_FakeFeedback(),
    )
    context = _context(
        profile_id=uuid4(), user_id=uuid4(), session_id=uuid4()
    )
    unbound = TurnContext(
        user_id=context.user_id,
        session_id=context.session_id,
        active_radar_ref=None,
        active_radar_version=None,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=("record_feedback",),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=context.correlation_id,
    )

    result = executor.execute(
        command=RecordFeedbackCommand(
            act_id="a1",
            listing_id=uuid4(),
            feedback_type="like",
        ),
        context=unbound,
        idempotency_key="conversation:session:message:a1",
    )

    assert result.status == "rejected"
    assert result.reason_code == "radar.not_bound"
