"""Runtime surface heartbeat persistence without repository-owned commits."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from umbral.infrastructure.db.models.runtime import RuntimeSurfaceStatus


class SqlAlchemyRuntimeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def heartbeat(
        self,
        *,
        environment: str,
        surface: str,
        release_id: str,
        manifest_sha256: str,
        artifact_digest: str,
        state: str,
        checks: dict[str, object],
        correlation_id: UUID,
        observed_at: datetime | None = None,
    ) -> RuntimeSurfaceStatus:
        timestamp = _utc(observed_at or datetime.now(timezone.utc))
        status = self.session.get(RuntimeSurfaceStatus, (environment, surface))
        if status is None:
            status = RuntimeSurfaceStatus(
                environment=environment,
                surface=surface,
                release_id=release_id,
                manifest_sha256=manifest_sha256,
                artifact_digest=artifact_digest,
                state=state,
                observed_at=timestamp,
                checks=checks,
                correlation_id=correlation_id,
            )
            self.session.add(status)
        else:
            status.release_id = release_id
            status.manifest_sha256 = manifest_sha256
            status.artifact_digest = artifact_digest
            status.state = state
            status.observed_at = timestamp
            status.checks = checks
            status.correlation_id = correlation_id
        self.session.flush()
        return status

    def is_stale(
        self,
        *,
        environment: str,
        surface: str,
        now: datetime | None = None,
        max_age: timedelta = timedelta(seconds=60),
    ) -> bool:
        status = self.session.get(RuntimeSurfaceStatus, (environment, surface))
        if status is None:
            return True
        timestamp = _utc(now or datetime.now(timezone.utc))
        return timestamp - status.observed_at > max_age


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = ["SqlAlchemyRuntimeRepository"]
