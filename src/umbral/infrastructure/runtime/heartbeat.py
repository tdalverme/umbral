"""Durable, per-surface release heartbeat writer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import uuid4

from sqlalchemy.orm import Session

from umbral.application.runtime.version import ReleaseManifest
from umbral.infrastructure.db.repositories.runtime import SqlAlchemyRuntimeRepository

HEARTBEAT_INTERVAL_SECONDS = 30


class RuntimeHeartbeatWriter:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        environment: str,
        release: ReleaseManifest,
    ) -> None:
        self._session_factory = session_factory
        self._environment = environment
        self._release = release

    def observe(
        self, surface: str, *, state: str, checks: Mapping[str, object]
    ) -> None:
        artifact = "web" if surface == "web" else "runtime"
        with self._session_factory() as session:
            SqlAlchemyRuntimeRepository(session).heartbeat(
                environment=self._environment,
                surface=surface,
                release_id=self._release.release_id,
                manifest_sha256=self._release.manifest_sha256,
                artifact_digest=self._release.artifacts[artifact].digest,
                state=state,
                checks=dict(checks),
                correlation_id=uuid4(),
            )
            session.commit()
