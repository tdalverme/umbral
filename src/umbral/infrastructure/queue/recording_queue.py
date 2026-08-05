"""Deterministic in-memory queue used by local runs and contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RecordedMessage:
    id: str
    payload: dict[str, object]


class RecordingJobQueue:
    """Record one JSON-safe message per deterministic execution/attempt ID."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._messages: list[RecordedMessage] = []

    @property
    def messages(self) -> list[RecordedMessage]:
        return self._messages

    def publish(
        self,
        *,
        execution_id: UUID,
        attempt_number: int,
        correlation_id: UUID,
    ) -> str:
        if attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        message_id = f"{execution_id}-{attempt_number}"
        message = RecordedMessage(
            id=message_id,
            payload={
                "execution_id": str(execution_id),
                "attempt_number": attempt_number,
                "correlation_id": str(correlation_id),
            },
        )
        with self._lock:
            if not any(item.id == message_id for item in self._messages):
                self._messages.append(message)
        return message_id

    def pop(self, message_id: str) -> RecordedMessage | None:
        with self._lock:
            for index, message in enumerate(self._messages):
                if message.id == message_id:
                    return self._messages.pop(index)
            return None

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
