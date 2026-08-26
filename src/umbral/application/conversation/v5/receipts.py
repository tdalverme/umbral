"""Durable command receipts and the idempotent execution guard (V5).

Receipts are the cross-command guard for commands without native idempotency
(preferences) and a safety net for the rest. A receipt left ``started`` after a
crash is reported as ``execution.reconciliation_required`` and handled
operationally instead of risking a duplicate mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from umbral.application.conversation.v5.contracts import (
    CommandV5,
    ExecutedActV5,
    TurnContextV5,
)
from umbral.application.conversation.v5.ports import EffectExecutorV5Like

ReceiptStartStatus = Literal["new", "already_applied", "in_progress"]


@dataclass(frozen=True, slots=True)
class ReceiptStart:
    status: ReceiptStartStatus
    result: ExecutedActV5 | None = None


class CommandReceiptStore(Protocol):
    def start(
        self,
        command: CommandV5,
        idempotency_key: str,
        *,
        correlation_id: UUID | None = None,
    ) -> ReceiptStart: ...

    def complete(self, idempotency_key: str, result: ExecutedActV5) -> None: ...

    def fail(self, idempotency_key: str, reason_code: str) -> None: ...


class InMemoryCommandReceiptStore:
    """Receipt store for unit tests and in-memory compositions."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[str, ExecutedActV5 | None, str | None]] = {}

    def start(
        self,
        command: CommandV5,
        idempotency_key: str,
        *,
        correlation_id: UUID | None = None,
    ) -> ReceiptStart:
        row = self._rows.get(idempotency_key)
        if row is not None:
            status, result, _ = row
            if status == "applied" and result is not None:
                return ReceiptStart("already_applied", result)
            if status == "started":
                return ReceiptStart("in_progress", None)
        self._rows[idempotency_key] = ("started", None, None)
        return ReceiptStart("new", None)

    def complete(self, idempotency_key: str, result: ExecutedActV5) -> None:
        self._rows[idempotency_key] = ("applied", result, None)

    def fail(self, idempotency_key: str, reason_code: str) -> None:
        self._rows[idempotency_key] = ("failed", None, reason_code)


def execute_with_receipt(
    *,
    store: CommandReceiptStore,
    executor: EffectExecutorV5Like,
    command: CommandV5,
    context: TurnContextV5,
    idempotency_key: str,
    correlation_id: UUID | None = None,
) -> ExecutedActV5:
    """Execute one command exactly once per idempotency key.

    Returns the stored result for an already-applied receipt, reports
    ``execution.reconciliation_required`` for an in-progress receipt, and
    otherwise runs the executor and records the outcome.
    """
    started = store.start(command, idempotency_key, correlation_id=correlation_id)
    if started.status == "already_applied" and started.result is not None:
        return started.result
    if started.status == "in_progress":
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key=_effect_key_for(command),
            status="rejected",
            reason_code="execution.reconciliation_required",
        )
    try:
        result = executor.execute(
            command=command, context=context, idempotency_key=idempotency_key
        )
    except Exception:
        store.fail(idempotency_key, "execution.failed")
        raise
    if result.status in ("applied", "pending"):
        store.complete(idempotency_key, result)
    else:
        store.fail(idempotency_key, result.reason_code or "execution.failed")
    return result


def _effect_key_for(command: CommandV5) -> str:
    from umbral.application.conversation.v5.contracts import (
        ClearFilterCommand,
        CreateRadarCommand,
        RecordDesireCommand,
        RecordFeedbackCommand,
        ReviseDesireCommand,
        SetFilterCommand,
        WithdrawDesireCommand,
    )

    if isinstance(command, CreateRadarCommand):
        return "radar.created"
    if isinstance(command, SetFilterCommand):
        return "filter.set"
    if isinstance(command, ClearFilterCommand):
        return "filter.cleared"
    if isinstance(command, RecordDesireCommand):
        return "desire.remembered"
    if isinstance(command, ReviseDesireCommand):
        return "desire.revised"
    if isinstance(command, WithdrawDesireCommand):
        return "desire.withdrawn"
    if isinstance(command, RecordFeedbackCommand):
        return "feedback.recorded"
    return "command.executed"
