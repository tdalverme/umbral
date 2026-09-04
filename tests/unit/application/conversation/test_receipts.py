"""Unit tests for V5 command receipts and the idempotent execution guard."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from umbral.application.conversation.contracts import (
    ExecutedAct,
    RecordDesireCommand,
    TurnContext,
)
from umbral.application.conversation.receipts import (
    InMemoryCommandReceiptStore,
    execute_with_receipt,
)

_KEY = "conversation:session:message:a1"


def _context() -> TurnContext:
    return TurnContext(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=("express_desire",),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id="correlation:1",
    )


class _FakeExecutor:
    def __init__(self, result: ExecutedAct) -> None:
        self._result = result
        self.calls = 0

    def execute(
        self,
        *,
        command: Any,
        context: Any,
        idempotency_key: str,
    ) -> ExecutedAct:
        self.calls += 1
        return self._result


def _command() -> RecordDesireCommand:
    return RecordDesireCommand(
        act_id="a1",
        raw_text="Quiero algo moderno",
        subject_ref="moderno",
    )


def test_receipt_replay_returns_stored_result_without_re_execution() -> None:
    store = InMemoryCommandReceiptStore()
    applied = ExecutedAct(
        act_id="a1", effect_key="desire.remembered", object_ref=f"desire:{uuid4()}"
    )
    executor = _FakeExecutor(applied)
    command = _command()

    first = execute_with_receipt(
        store=store,
        executor=executor,
        command=command,
        context=_context(),
        idempotency_key=_KEY,
    )
    second = execute_with_receipt(
        store=store,
        executor=executor,
        command=command,
        context=_context(),
        idempotency_key=_KEY,
    )

    assert first == applied
    assert second == applied
    assert executor.calls == 1


def test_in_progress_receipt_reports_reconciliation_required() -> None:
    store = InMemoryCommandReceiptStore()
    applied = ExecutedAct(
        act_id="a1", effect_key="desire.remembered", object_ref=f"desire:{uuid4()}"
    )
    executor = _FakeExecutor(applied)
    command = _command()
    execute_with_receipt(
        store=store,
        executor=executor,
        command=command,
        context=_context(),
        idempotency_key=_KEY,
    )
    store._rows[_KEY] = ("started", None, None)  # simulate a crash before completion

    result = execute_with_receipt(
        store=store,
        executor=executor,
        command=command,
        context=_context(),
        idempotency_key=_KEY,
    )

    assert result.status == "rejected"
    assert result.reason_code == "execution.reconciliation_required"
    assert executor.calls == 1


def test_failed_receipt_allows_a_fresh_attempt() -> None:
    store = InMemoryCommandReceiptStore()
    store._rows[_KEY] = ("failed", None, "execution.failed")
    applied = ExecutedAct(
        act_id="a1", effect_key="desire.remembered", object_ref=f"desire:{uuid4()}"
    )
    executor = _FakeExecutor(applied)

    result = execute_with_receipt(
        store=store,
        executor=executor,
        command=_command(),
        context=_context(),
        idempotency_key=_KEY,
    )

    assert result == applied
    assert executor.calls == 1


def test_rejected_execution_marks_receipt_failed_and_returns_result() -> None:
    store = InMemoryCommandReceiptStore()
    rejected = ExecutedAct(
        act_id="a1",
        effect_key="desire.remembered",
        status="rejected",
        reason_code="radar.not_bound",
    )
    executor = _FakeExecutor(rejected)

    result = execute_with_receipt(
        store=store,
        executor=executor,
        command=_command(),
        context=_context(),
        idempotency_key=_KEY,
    )

    assert result == rejected
    assert store._rows[_KEY][0] == "failed"