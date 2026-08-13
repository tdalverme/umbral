"""Product events persistence and validation against real Postgres."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from tests.integration.radar.conftest import (
    build_radar_service,
    seed_user,
)

from umbral.application.radar.contracts import RadarValidationError

OWNER = uuid4()


def _events_of(factory: Any) -> list[dict[str, object]]:
    from sqlalchemy import select

    from umbral.infrastructure.db.models.radar import ProductEventRow

    with factory() as session:
        rows = session.scalars(select(ProductEventRow))
        return [{"event_type": row.event_type, "payload": row.payload} for row in rows]


def test_client_events_persist_after_registry_validation(radar_backend: Any) -> None:
    factory = radar_backend
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    profile, _ = service.create_profile(
        owner_id=user_id,
        name="Radar eventos",
        zones=("palermo",),
        budget_max=1000.0,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )

    event = service.record_client_event(
        event_type="recommendation.impression.v1",
        payload={
            "search_profile_id": str(profile.profile_id),
            "run_id": str(uuid4()),
            "listing_id": str(uuid4()),
        },
        actor_id=user_id,
        correlation_id=uuid4(),
    )
    assert event.event_type == "recommendation.impression.v1"
    assert event.event_version == 1

    rows = _events_of(factory)
    types = [row["event_type"] for row in rows]
    assert "radar.created.v1" in types
    assert "recommendation.impression.v1" in types


def test_invalid_client_event_is_rejected_without_rows(radar_backend: Any) -> None:
    factory = radar_backend
    user_id = seed_user(factory)
    service = build_radar_service(factory)
    seed_user(factory)

    with pytest.raises(RadarValidationError) as excinfo:
        service.record_client_event(
            event_type="chat.sent.v1",
            payload={},
            actor_id=user_id,
            correlation_id=uuid4(),
        )
    assert excinfo.value.error_codes == ("events.unknown_type",)

    with pytest.raises(RadarValidationError):
        service.record_client_event(
            event_type="recommendation.impression.v1",
            payload={
                "search_profile_id": str(uuid4()),
                "run_id": str(uuid4()),
                "listing_id": str(uuid4()),
                "email": "pii@example.invalid",
            },
            actor_id=user_id,
            correlation_id=uuid4(),
        )
    rows = _events_of(factory)
    assert all(row["event_type"] != "chat.sent.v1" for row in rows)
