"""Sanitized PostgreSQL, extension and Alembic readiness probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Engine, text

ReadinessState = Literal["ready", "degraded", "not_ready"]
DatabaseState = Literal["ready", "degraded", "unavailable"]


@dataclass(frozen=True, slots=True)
class DatabaseReadiness:
    state: DatabaseState
    code: str | None
    details: dict[str, str]

    def __post_init__(self) -> None:
        if self.state == "ready" and self.code is not None:
            raise ValueError("ready database checks cannot carry a failure code")
        if self.state != "ready" and self.code not in {
            "postgres.degraded",
            "postgres.unavailable",
        }:
            raise ValueError("database readiness code is not allowlisted")
        if set(self.details) - {"extension_postgis", "extension_vector"}:
            raise ValueError("database readiness details are not allowlisted")


@dataclass(frozen=True, slots=True)
class PersistenceCheck:
    state: ReadinessState
    code: str | None = None


@dataclass(frozen=True, slots=True)
class PersistenceReport:
    state: ReadinessState
    checks: dict[str, PersistenceCheck]
    alembic_head: str | None


class PersistenceProbe:
    """Evaluate injected values or a SQLAlchemy engine without side effects."""

    def __init__(
        self,
        *,
        database: DatabaseReadiness,
        alembic_head: str | None,
    ) -> None:
        self.database = database
        self.alembic_head = alembic_head

    def evaluate(self) -> PersistenceReport:
        database_state: ReadinessState = (
            "not_ready" if self.database.state == "unavailable" else self.database.state
        )
        database_check = PersistenceCheck(database_state, self.database.code)
        extension_checks = {
            "postgis": PersistenceCheck(
                "ready"
                if self.database.details.get("extension_postgis") == "ready"
                else "not_ready",
                None
                if self.database.details.get("extension_postgis") == "ready"
                else "postgis.unavailable",
            ),
            "pgvector": PersistenceCheck(
                "ready"
                if self.database.details.get("extension_vector") == "ready"
                else "not_ready",
                None
                if self.database.details.get("extension_vector") == "ready"
                else "pgvector.unavailable",
            ),
        }
        alembic_check = PersistenceCheck(
            "ready" if self.alembic_head else "not_ready",
            None if self.alembic_head else "alembic.unavailable",
        )
        checks = {
            "postgres": database_check,
            **extension_checks,
            "alembic": alembic_check,
        }
        if any(check.state == "not_ready" for check in checks.values()):
            state: ReadinessState = "not_ready"
        elif any(check.state == "degraded" for check in checks.values()):
            state = "degraded"
        else:
            state = "ready"
        return PersistenceReport(
            state=state, checks=checks, alembic_head=self.alembic_head
        )

    @classmethod
    def from_engine(cls, engine: Engine, *, expected_head: str) -> PersistenceProbe:
        """Run only bounded metadata queries; failures become safe codes."""

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                rows = connection.execute(
                    text(
                        "SELECT extname FROM pg_extension "
                        "WHERE extname IN ('postgis', 'vector')"
                    )
                )
                extensions = {str(row[0]) for row in rows}
                alembic = (
                    connection.execute(
                        text("SELECT version_num FROM alembic_version LIMIT 2")
                    )
                    .scalars()
                    .all()
                )
            database = DatabaseReadiness(
                state="ready",
                code=None,
                details={
                    "extension_postgis": "ready"
                    if "postgis" in extensions
                    else "unavailable",
                    "extension_vector": "ready"
                    if "vector" in extensions
                    else "unavailable",
                },
            )
            head = expected_head if alembic == [expected_head] else None
        except Exception:
            database = DatabaseReadiness(
                state="unavailable",
                code="postgres.unavailable",
                details={},
            )
            head = None
        return cls(database=database, alembic_head=head)
