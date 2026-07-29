"""Small in-process deployment lock used by local promotion drills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class ReleaseLockBusy(RuntimeError):
    """Raised when another unexpired owner holds an environment lock."""


@dataclass(frozen=True)
class LockRecord:
    environment: str
    owner: str
    release_id: str
    expires_at: datetime


class ReleaseLock:
    def __init__(self) -> None:
        self._records: dict[str, LockRecord] = {}

    def acquire(
        self,
        environment: str,
        *,
        owner: str,
        release_id: str,
        now: datetime | None = None,
        ttl: timedelta = timedelta(minutes=15),
    ) -> LockRecord:
        instant = now or datetime.now(timezone.utc)
        current = self._records.get(environment)
        if current is not None and current.expires_at > instant:
            raise ReleaseLockBusy(f"environment {environment} is locked")
        record = LockRecord(environment, owner, release_id, instant + ttl)
        self._records[environment] = record
        return record

    def owner(self, environment: str, *, now: datetime | None = None) -> str | None:
        instant = now or datetime.now(timezone.utc)
        current = self._records.get(environment)
        if current is None or current.expires_at <= instant:
            return None
        return current.owner

    def release(self, environment: str, *, owner: str) -> None:
        current = self._records.get(environment)
        if current is not None and current.owner == owner:
            del self._records[environment]
