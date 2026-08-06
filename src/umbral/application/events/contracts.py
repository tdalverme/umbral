"""Pure, transport-independent values for versioned product events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProductEvent:
    """One validated, versioned product event without PII."""

    event_id: UUID
    event_type: str
    event_version: int
    actor_id: UUID | None
    occurred_at: datetime
    correlation_id: UUID
    payload: Mapping[str, object]
