"""Unit tests for the SQLAlchemy V5 command receipt store."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from umbral.application.conversation.v5.contracts import (
    ExecutedActV5,
    RecordDesireCommand,
)
from umbral.infrastructure.db.models.conversation_v5 import (
    ConversationV5CommandReceipt,
)
from umbral.infrastructure.db.repositories.conversation_v5 import (
    SqlAlchemyCommandReceiptStore,
)

SessionFactory = Callable[[], Session]


class _FakeSession:
    def __init__(self, store: dict[str, ConversationV5CommandReceipt]) -> None:
        self._store = store
        self.committed = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(
        self, model: type[ConversationV5CommandReceipt], pk: str
    ) -> ConversationV5CommandReceipt | None:
        return self._store.get(pk)

    def add(self, row: ConversationV5CommandReceipt) -> None:
        self._store[row.idempotency_key] = row

    def commit(self) -> None:
        self.committed = True


def _factory(
    store: dict[str, ConversationV5CommandReceipt],
) -> SessionFactory:
    def make() -> Session:
        return cast(Session, _FakeSession(store))

    return make


def _command() -> RecordDesireCommand:
    return RecordDesireCommand(
        act_id="a1",
        raw_text="Quiero algo moderno",
        subject_ref="moderno",
    )


def _key() -> str:
    session_id = uuid4()
    message_id = uuid4()
    return f"conversation-v5:{session_id}:{message_id}:a1"


def test_start_creates_started_receipt_then_complete_marks_applied() -> None:
    store: dict[str, ConversationV5CommandReceipt] = {}
    receipts = SqlAlchemyCommandReceiptStore(_factory(store))
    key = _key()

    started = receipts.start(_command(), key, correlation_id=uuid4())
    assert started.status == "new"

    result = ExecutedActV5(
        act_id="a1",
        effect_key="desire.remembered",
        object_ref=f"desire:{uuid4()}",
    )
    receipts.complete(key, result)

    replay = receipts.start(_command(), key, correlation_id=uuid4())
    assert replay.status == "already_applied"
    assert replay.result == result
    assert store[key].status == "applied"


def test_start_returns_in_progress_for_unfinished_receipt() -> None:
    store: dict[str, ConversationV5CommandReceipt] = {}
    receipts = SqlAlchemyCommandReceiptStore(_factory(store))
    key = _key()
    receipts.start(_command(), key, correlation_id=uuid4())

    replay = receipts.start(_command(), key, correlation_id=uuid4())

    assert replay.status == "in_progress"
    assert store[key].status == "started"


def test_fail_marks_receipt_failed_and_permits_retry() -> None:
    store: dict[str, ConversationV5CommandReceipt] = {}
    receipts = SqlAlchemyCommandReceiptStore(_factory(store))
    key = _key()
    receipts.start(_command(), key, correlation_id=uuid4())
    receipts.fail(key, "radar.not_bound")

    assert store[key].status == "failed"
    assert store[key].result == {"reason_code": "radar.not_bound"}

    retry = receipts.start(_command(), key, correlation_id=uuid4())
    assert retry.status == "new"
    assert store[key].status == "started"