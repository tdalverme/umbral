"""Application transaction ports with one owner for commit and rollback."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol, TypeVar

SessionT = TypeVar("SessionT")


class TransactionStateError(RuntimeError):
    """Raised when transaction lifecycle methods are called out of order."""


class UnitOfWork(Protocol[SessionT]):
    """A transaction-scoped application unit, never a generic repository."""

    session: SessionT

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class TransactionManager(Protocol[SessionT]):
    """Port used by application services to open transaction scopes."""

    def transaction(self) -> AbstractContextManager[UnitOfWork[SessionT]]: ...


@contextmanager
def transaction_scope(
    manager: TransactionManager[Any] | None,
) -> Iterator[UnitOfWork[Any] | None]:
    """Open the supplied transaction manager or a no-op local scope.

    Application services can use this helper without knowing whether the
    composition root supplied the SQLAlchemy transaction adapter or a local
    in-memory runtime.  The manager, when present, remains the sole owner of
    commit and rollback.
    """

    if manager is None:
        yield None
        return
    with manager.transaction() as transaction:
        yield transaction


class _TransactionAdapter(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class InMemoryUnitOfWork(AbstractContextManager["InMemoryUnitOfWork"]):
    """A tiny deterministic adapter for application tests."""

    def __init__(self, manager: object, transaction: _TransactionAdapter) -> None:
        self._manager = manager
        self._transaction = transaction
        self.session = transaction
        self._entered = False
        self._finished = False

    def __enter__(self) -> InMemoryUnitOfWork:
        if self._entered:
            raise TransactionStateError("transaction already entered")
        self._entered = True
        return self

    def write(self, key: str, value: str) -> None:
        writer = getattr(self._transaction, "write", None)
        if writer is None:
            raise TransactionStateError("transaction does not support writes")
        writer(key, value)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()

    def commit(self) -> None:
        if not self._entered or self._finished:
            raise TransactionStateError("transaction is not active")
        self._transaction.commit()
        self._finished = True

    def rollback(self) -> None:
        if not self._entered or self._finished:
            raise TransactionStateError("transaction is not active")
        self._transaction.rollback()
        self._finished = True

    def close(self) -> None:
        if not self._entered:
            raise TransactionStateError("transaction is not active")
        if not self._finished:
            self._transaction.rollback()
        self._transaction.close()
        self._finished = True
