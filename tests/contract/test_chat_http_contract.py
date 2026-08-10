"""Chat HTTP contract: OpenAPI surface, SSE serialization and error mapping (T032)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from umbral.agent.events import (
    InterruptWaiting,
    ReplyFragment,
    RunCompleted,
    RunFailed,
    RunInterrupted,
    RunStarted,
    ToolActivity,
)
from umbral.api.routers.chat import _serialize_event

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = json.loads(
    (ROOT / "contracts" / "openapi" / "v1" / "openapi.json").read_text(
        encoding="utf-8"
    )
)

CHAT_PATHS = {
    "/api/v1/chat/sessions",
    "/api/v1/chat/sessions/{session_id}",
    "/api/v1/chat/sessions/{session_id}/messages",
    "/api/v1/chat/sessions/{session_id}/resume",
    "/api/v1/chat/sessions/{session_id}/runs/{run_id}/decision",
    "/api/v1/search-profiles/{search_profile_id}/update-proposals",
}


def test_openapi_declares_chat_paths() -> None:
    paths = set(OPENAPI["paths"])
    assert CHAT_PATHS.issubset(paths)


def test_openapi_declares_chat_operations() -> None:
    operations = {
        operation.get("operationId")
        for path_item in OPENAPI["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict)
    }
    assert "createSession" in operations
    assert "listChatSessions" in operations
    assert "getChatSession" in operations
    assert "listChatSessionMessages" in operations
    assert "sendChatMessage" in operations
    assert "resumeChatSession" in operations
    assert "decideChatRun" in operations
    assert "listUpdateProposals" in operations


def test_serialize_event_uses_sse_envelope() -> None:
    event = RunStarted(
        run_id=UUID(int=1), session_id=UUID(int=2), correlation_id=UUID(int=3)
    )
    line = _serialize_event(event, 0)
    assert line is not None
    assert line.startswith("event: chat.run_started\nid: 0\ndata: {")
    assert '"run_id"' in line


def test_serialize_event_covers_all_types() -> None:
    run_id = UUID(int=1)
    cases: list[tuple[object, str]] = [
        (RunStarted(run_id, UUID(int=2), UUID(int=3)), "chat.run_started"),
        (ReplyFragment(run_id, "hola"), "chat.reply_fragment"),
        (ToolActivity(run_id, "find_matches", "ok"), "chat.tool_activity"),
        (
            InterruptWaiting(run_id, {"type": "proposal_decision", "proposal_id": "p"}),
            "chat.interrupt_waiting",
        ),
        (RunCompleted(run_id, UUID(int=4)), "chat.run_completed"),
        (RunFailed(run_id, "agent.failed"), "chat.run_failed"),
        (RunInterrupted(run_id), "chat.run_interrupted"),
    ]
    for index, (event, expected) in enumerate(cases):
        line = _serialize_event(cast(Any, event), index)
        assert line is not None
        assert line.startswith(f"event: {expected}\nid: {index}\n")
