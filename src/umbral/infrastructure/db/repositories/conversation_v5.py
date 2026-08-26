"""SQLAlchemy repository for V5 command receipts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session

from umbral.application.conversation.v5.contracts import (
    CommandV5,
    ExecutedActV5,
    OutcomeStatusV5,
)
from umbral.application.conversation.v5.receipts import (
    ReceiptStart,
)
from umbral.infrastructure.db.models.conversation_v5 import (
    ConversationV5CommandReceipt,
)

SessionFactory = Callable[[], Session]

_KEY_PREFIX = "conversation-v5:"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyCommandReceiptStore:
    """Command receipt store backed by the durable receipts table."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def start(
        self,
        command: CommandV5,
        idempotency_key: str,
        *,
        correlation_id: UUID | None = None,
    ) -> ReceiptStart:
        with self.session_factory() as current:
            model = current.get(ConversationV5CommandReceipt, idempotency_key)
            if model is not None:
                if model.status == "applied" and model.result is not None:
                    return ReceiptStart("already_applied", _result_from(model.result))
                if model.status == "started":
                    return ReceiptStart("in_progress", None)
            session_id, message_id = _ids_from_key(idempotency_key)
            now = _now()
            current.add(
                ConversationV5CommandReceipt(
                    idempotency_key=idempotency_key,
                    session_id=session_id,
                    message_id=message_id,
                    act_id=command.act_id,
                    command_kind=type(command).__name__,
                    status="started",
                    result=None,
                    correlation_id=correlation_id or UUID(int=0),
                    created_at=now,
                    updated_at=now,
                )
            )
            current.commit()
            return ReceiptStart("new", None)

    def complete(self, idempotency_key: str, result: ExecutedActV5) -> None:
        with self.session_factory() as current:
            model = current.get(ConversationV5CommandReceipt, idempotency_key)
            if model is None:
                return
            model.status = "applied"
            model.result = _serialize_result(result)
            model.updated_at = _now()
            current.commit()

    def fail(self, idempotency_key: str, reason_code: str) -> None:
        with self.session_factory() as current:
            model = current.get(ConversationV5CommandReceipt, idempotency_key)
            if model is None:
                return
            model.status = "failed"
            model.result = {"reason_code": reason_code}
            model.updated_at = _now()
            current.commit()


def _ids_from_key(idempotency_key: str) -> tuple[UUID, UUID]:
    rest = idempotency_key.removeprefix(_KEY_PREFIX)
    session_id, message_id = rest.split(":", 2)[:2]
    return UUID(session_id), UUID(message_id)


def _serialize_result(result: ExecutedActV5) -> dict[str, object]:
    return {
        "act_id": result.act_id,
        "effect_key": result.effect_key,
        "status": result.status,
        "object_ref": result.object_ref,
        "reason_code": result.reason_code,
    }


def _result_from(data: Mapping[str, object]) -> ExecutedActV5:
    return ExecutedActV5(
        act_id=str(data["act_id"]),
        effect_key=str(data["effect_key"]),
        status=cast(OutcomeStatusV5, data["status"]),
        object_ref=cast(str | None, data.get("object_ref")),
        reason_code=cast(str | None, data.get("reason_code")),
    )
