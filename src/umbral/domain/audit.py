"""Pure audit and identity values shared by persistence operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

ActorKind = Literal["system", "service", "operator"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class RecordIdentity:
    """Application-generated identity and optimistic-lock fields."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    version: int = 1

    def __post_init__(self) -> None:
        created_at = _utc(self.created_at)
        updated_at = _utc(self.updated_at)
        if updated_at < created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.version < 1:
            raise ValueError("version must be positive")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)

    @classmethod
    def new(
        cls, *, now: datetime | None = None, id: UUID | None = None
    ) -> RecordIdentity:
        timestamp = _utc(now or datetime.now(timezone.utc))
        return cls(id=id or uuid4(), created_at=timestamp, updated_at=timestamp)


@dataclass(frozen=True, slots=True)
class AuditActor:
    """Closed actor identity; system work has no actor id."""

    kind: ActorKind
    id: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "system":
            if self.id is not None:
                raise ValueError("system actors cannot carry an actor id")
            return
        if self.id is None or not self.id.strip() or len(self.id) > 128:
            raise ValueError("service and operator actors require a bounded id")
        if any(character.isspace() for character in self.id):
            raise ValueError("actor id cannot contain whitespace")

    @classmethod
    def system(cls) -> AuditActor:
        return cls(kind="system")


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Normalized mutation provenance without request or exception payloads."""

    actor: AuditActor
    source: str
    correlation_id: UUID

    def __post_init__(self) -> None:
        if not self.source or len(self.source) > 128:
            raise ValueError("source must be 1..128 characters")
        if any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789._-"
            for character in self.source
        ):
            raise ValueError("source must be a stable lowercase operation code")
