"""Serialization helpers for process-local playground evidence."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


def primitive(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (UUID, datetime, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    if is_dataclass(value):
        return primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [primitive(item) for item in value]
    return str(value)


def event_record(event: object) -> dict[str, object]:
    data = primitive(event)
    return data if isinstance(data, dict) else {"value": data}
