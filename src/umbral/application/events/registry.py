"""Closed product events registry v1.

The registry is loaded from ``contracts/events/v1/events-registry.json`` and
passed in as a :class:`EventsRegistrySpec`. Event types are closed: unknown
types, missing required keys, forbidden PII keys and extra keys are rejected
with a stable error code. The pattern mirrors ``domain/identity/events.py``
for product events.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

VALID_ERRORS = (
    "events.unknown_type",
    "events.missing_keys",
    "events.forbidden_keys",
    "events.extra_keys",
)


@dataclass(frozen=True, slots=True)
class EventTypeSpec:
    name: str
    version: int
    emitted_by: str
    required_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventsRegistrySpec:
    contract_version: str
    registry_version: str
    event_types: Mapping[str, EventTypeSpec]
    forbidden_keys: frozenset[str]
    common_fields: tuple[str, ...]


def parse_events_registry(data: Mapping[str, object]) -> EventsRegistrySpec:
    if data.get("contract_version") != "1":
        raise ValueError("unsupported events registry document version")
    registry_version = data.get("registry_version")
    if not isinstance(registry_version, str) or not registry_version:
        raise ValueError("registry_version is required")

    raw_types = data.get("event_types")
    if not isinstance(raw_types, Mapping):
        raise ValueError("event types are required")
    event_types: dict[str, EventTypeSpec] = {}
    for name, raw in raw_types.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"event type {name!r} must be an object")
        required = raw.get("required_keys")
        event_types[str(name)] = EventTypeSpec(
            name=str(name),
            version=_as_int(raw.get("version"), 1),
            emitted_by=str(raw.get("emitted_by", "server")),
            required_keys=(
                tuple(str(item) for item in required)
                if isinstance(required, list)
                else ()
            ),
        )

    raw_forbidden = data.get("forbidden_keys")
    forbidden = (
        frozenset(str(item) for item in raw_forbidden)
        if isinstance(raw_forbidden, list)
        else frozenset()
    )
    raw_common = data.get("common_fields")
    common = (
        tuple(str(item) for item in raw_common) if isinstance(raw_common, list) else ()
    )

    return EventsRegistrySpec(
        contract_version=str(data["contract_version"]),
        registry_version=registry_version,
        event_types=event_types,
        forbidden_keys=forbidden,
        common_fields=common,
    )


def validate_event(
    spec: EventsRegistrySpec, event_type: str, payload: Mapping[str, object]
) -> str | None:
    """Return the error code of an invalid event payload, or None when valid."""
    type_spec = spec.event_types.get(event_type)
    if type_spec is None:
        return "events.unknown_type"

    if not isinstance(payload, Mapping):
        return "events.extra_keys"

    missing = [key for key in type_spec.required_keys if key not in payload]
    if missing:
        return "events.missing_keys"

    forbidden = [key for key in payload if key in spec.forbidden_keys]
    if forbidden:
        return "events.forbidden_keys"

    allowed = set(type_spec.required_keys)
    extra = [key for key in payload if key not in allowed]
    if extra:
        return "events.extra_keys"

    return None


def event_version(spec: EventsRegistrySpec, event_type: str) -> int | None:
    type_spec = spec.event_types.get(event_type)
    if type_spec is None:
        return None
    return type_spec.version


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
