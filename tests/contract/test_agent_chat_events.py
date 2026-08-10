"""Chat product events registry conformance (DoD #4, FR-018)."""

from __future__ import annotations

from umbral.infrastructure.radar.contract_loader import load_events_registry


def test_chat_events_are_registered() -> None:
    registry = load_events_registry()
    assert "chat.session_created.v1" in registry.event_types
    assert "chat.message_created.v1" in registry.event_types
    assert registry.event_types["chat.session_created.v1"].version == 1
    assert registry.event_types["chat.message_created.v1"].version == 1


def test_chat_session_created_payload_validation() -> None:
    from umbral.application.events.registry import validate_event

    registry = load_events_registry()
    assert (
        validate_event(
            registry,
            "chat.session_created.v1",
            {"session_id": "s1", "search_profile_id": "p1"},
        )
        is None
    )
    assert (
        validate_event(registry, "chat.session_created.v1", {"session_id": "s1"})
        == "events.missing_keys"
    )
    assert (
        validate_event(
            registry,
            "chat.session_created.v1",
            {"session_id": "s1", "search_profile_id": "p1", "extra": 1},
        )
        == "events.extra_keys"
    )


def test_chat_message_created_payload_validation() -> None:
    from umbral.application.events.registry import validate_event

    registry = load_events_registry()
    assert (
        validate_event(
            registry,
            "chat.message_created.v1",
            {"session_id": "s1", "message_id": "m1", "role": "user"},
        )
        is None
    )
    # Message text must never be an allowed key (0 PII in payloads).
    assert (
        validate_event(
            registry,
            "chat.message_created.v1",
            {"session_id": "s1", "message_id": "m1", "role": "user", "text": "hola"},
        )
        == "events.extra_keys"
    )


def test_unknown_event_type_is_rejected() -> None:
    from umbral.application.events.registry import validate_event

    registry = load_events_registry()
    assert validate_event(registry, "chat.unknown.v1", {}) == "events.unknown_type"
