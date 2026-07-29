"""SQLAlchemy transaction adapter; only this boundary may commit."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from umbral.application.transactions import TransactionStateError
from umbral.domain.errors import ConcurrencyConflict


def translate_stale_data_error(
    error: StaleDataError,
    *,
    expected_version: int | None = None,
    actual_version: int | None = None,
) -> ConcurrencyConflict:
    """Convert SQLAlchemy's row-count failure into the domain conflict type."""

    del error
    return ConcurrencyConflict(
        expected_version=expected_version,
        actual_version=actual_version,
    )


class SqlAlchemyUnitOfWork(AbstractContextManager["SqlAlchemyUnitOfWork"]):
    """One Session and transaction scope; no repository-level commit API."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._entered = False
        self._finished = False

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        if self._entered:
            raise TransactionStateError("transaction already entered")
        self._entered = True
        self.session.begin()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()

    def commit(self) -> None:
        self._require_active()
        try:
            self.session.commit()
        except StaleDataError as error:
            self.session.rollback()
            self._finished = True
            raise translate_stale_data_error(error) from error
        self._finished = True

    def rollback(self) -> None:
        self._require_active()
        self.session.rollback()
        self._finished = True

    def close(self) -> None:
        if not self._entered:
            raise TransactionStateError("transaction is not active")
        if not self._finished:
            self.session.rollback()
        self.session.close()
        self._finished = True

    def _require_active(self) -> None:
        if not self._entered or self._finished:
            raise TransactionStateError("transaction is not active")


class SqlAlchemyTransactionManager:
    """Application transaction manager backed by a Session factory."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def transaction(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory())
