"""Unit tests for the persisted explanation narrative cache."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.orm import Session

from umbral.application.scoring.narrative import ExplanationNarrative
from umbral.infrastructure.db.repositories.scoring import (
    SqlAlchemyExplanationNarrativeCache,
)


class _CapturingSession:
    def __init__(self) -> None:
        self.statement: Any = None
        self.committed = False

    def __enter__(self) -> _CapturingSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, statement: Any) -> None:
        self.statement = statement

    def commit(self) -> None:
        self.committed = True


def test_put_updates_existing_cache_key_instead_of_ignoring_new_narrative() -> None:
    session = _CapturingSession()
    cache = SqlAlchemyExplanationNarrativeCache(
        lambda: cast(Session, session)
    )

    cache.put(
        run_id=uuid4(),
        listing_id=uuid4(),
        prompt_version="explanation-narrative-v2",
        model_version="gpt-4.1-mini",
        schema_version="explanation-narrative-v1",
        narrative=ExplanationNarrative(
            text="Tiene buena conectividad para esta búsqueda.",
            used_criteria=("ubicacion",),
            used_evidence_refs=("urban:transit_access",),
            source="managed",
            prompt_version="explanation-narrative-v2",
            model_version="gpt-4.1-mini",
        ),
        now=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )

    sql = str(session.statement.compile(dialect=dialect()))
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET" in sql
    assert session.committed is True
