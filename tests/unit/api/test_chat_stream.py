"""Regression tests for terminal chat SSE behavior."""

from __future__ import annotations

from uuid import uuid4

import pytest

from umbral.api.routers import chat
from umbral.application.chat.contracts import ChatExecutionInProgress


@pytest.mark.asyncio
async def test_stream_turn_closes_and_reports_concurrent_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid4()

    class _Runtime:
        def run_turn(self, **_: object) -> None:
            raise ChatExecutionInProgress(run_id)

    monkeypatch.setattr(chat, "_runtime", lambda: _Runtime())
    response = chat._stream_turn(
        user_id=uuid4(),
        session_id=uuid4(),
        text="mensaje",
        correlation_id=uuid4(),
    )

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    payload = "".join(chunks)
    assert "event: chat.run_failed" in payload
    assert '"error_code": "chat.execution_in_progress"' in payload
    assert str(run_id) in payload
