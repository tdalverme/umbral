"""Per-execution SQLAlchemy engine and session construction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_for_execution(database_url: str, **kwargs: Any) -> Engine:
    """Create a fresh engine for one runtime process; callers own its disposal."""

    options: dict[str, Any] = {
        "pool_pre_ping": True,
        "future": True,
    }
    options.update(kwargs)
    return create_engine(database_url, **options)


def create_session_factory(engine: Engine) -> Callable[[], Session]:
    """Return an unshared Session factory bound to the provided engine."""

    return sessionmaker(
        bind=engine, class_=Session, expire_on_commit=False, autoflush=True
    )


class SessionProvider:
    """Lazy per-execution engine/session provider with explicit close."""

    def __init__(self, database_url: str, **engine_options: Any) -> None:
        self.engine = create_engine_for_execution(database_url, **engine_options)
        self.session_factory = create_session_factory(self.engine)

    def session(self) -> Session:
        return self.session_factory()

    def close(self) -> None:
        self.engine.dispose()
