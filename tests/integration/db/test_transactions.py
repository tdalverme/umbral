"""Transaction boundary contracts (T038)."""

from __future__ import annotations

import pytest

from tests.fakes.transactions import InMemoryTransactionManager
from umbral.application.transactions import TransactionStateError


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

