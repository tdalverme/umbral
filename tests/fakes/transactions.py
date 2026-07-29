"""Tiny transaction fakes used to prove application boundaries."""

from __future__ import annotations

from dataclasses import dataclass


class InMemoryTransaction:
    def __init__(self, manager: InMemoryTransactionManager) -> None:
        self._manager = manager
        self._writes: dict[str, str] = {}

    def write(self, key: str, value: str) -> None:
        self._writes[key] = value

    def commit(self) -> None:
        self._manager._commit_writes(self._writes)

    def rollback(self) -> None:
        self._writes.clear()

    def close(self) -> None:
        self._writes.clear()


class InMemoryTransactionManager:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0
        self._active: InMemoryTransaction | None = None

    def transaction(self) -> InMemoryTransaction:
        from umbral.application.transactions import InMemoryUnitOfWork

        self._active = InMemoryTransaction(self)
        return InMemoryUnitOfWork(self, self._active)

    def commit(self) -> None:
        if self._active is None:
            from umbral.application.transactions import TransactionStateError

            raise TransactionStateError("no active transaction")
        self._active.commit()

    def _commit_writes(self, writes: dict[str, str]) -> None:
        self.data.update(writes)
        self.commits += 1

    def _rollback(self) -> None:
        self.rollbacks += 1

    def _close(self) -> None:
        self.closed += 1
        self._active = None


@dataclass
class InMemoryVersionedRecord:
    value: str
    version: int = 1

    def snapshot(self) -> InMemoryVersionedRecord:
        return InMemoryVersionedRecord(self.value, self.version)

    def update(self, expected_version: int, value: str) -> None:
        from umbral.domain.errors import ConcurrencyConflict

        if expected_version != self.version:
            raise ConcurrencyConflict(
                expected_version=expected_version,
                actual_version=self.version,
            )
        self.value = value
        self.version += 1
