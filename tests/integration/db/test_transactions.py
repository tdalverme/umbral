"""Transaction boundary contracts (T038)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm.exc import StaleDataError
from tests.fakes.transactions import InMemoryTransactionManager

from umbral.application.transactions import TransactionStateError
from umbral.domain.errors import ConcurrencyConflict
from umbral.infrastructure.db.transaction import SqlAlchemyUnitOfWork


def test_transaction_commits_once_and_closes() -> None:
    manager = InMemoryTransactionManager()

    with manager.transaction() as transaction:
        transaction.write("value", "committed")

    assert manager.commits == 1
    assert manager.rollbacks == 0
    assert manager.closed == 1
    assert manager.data == {"value": "committed"}


def test_transaction_rolls_back_and_closes_on_error() -> None:
    manager = InMemoryTransactionManager()

    with pytest.raises(RuntimeError):
        with manager.transaction() as transaction:
            transaction.write("value", "discarded")
            raise RuntimeError("boom")

    assert manager.commits == 0
    assert manager.rollbacks == 1
    assert manager.closed == 1
    assert manager.data == {}


def test_transaction_manager_rejects_commit_outside_context() -> None:
    manager = InMemoryTransactionManager()

    with pytest.raises(TransactionStateError):
        manager.commit()


def test_uow_does_not_expose_repository_commit() -> None:
    manager = InMemoryTransactionManager()

    with manager.transaction() as transaction:
        assert not hasattr(transaction, "repository_commit")


class _SessionStub:
    def __init__(self, *, stale_on_commit: bool = False) -> None:
        self.calls: list[str] = []
        self.stale_on_commit = stale_on_commit

    def begin(self) -> None:
        self.calls.append("begin")

    def commit(self) -> None:
        self.calls.append("commit")
        if self.stale_on_commit:
            raise StaleDataError("row count changed")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


def test_sqlalchemy_uow_owns_begin_commit_and_close() -> None:
    session = _SessionStub()

    with SqlAlchemyUnitOfWork(session):  # type: ignore[arg-type]
        pass

    assert session.calls == ["begin", "commit", "close"]


def test_sqlalchemy_stale_data_is_translated_to_typed_conflict() -> None:
    session = _SessionStub(stale_on_commit=True)

    with pytest.raises(ConcurrencyConflict) as raised:
        with SqlAlchemyUnitOfWork(session):  # type: ignore[arg-type]
            pass

    assert raised.value.code == "concurrency.conflict"
    assert session.calls == ["begin", "commit", "rollback", "close"]
