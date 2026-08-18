"""Agent tool stack composition for tests and the harness (H4.2, R-12).

No HTTP surface is wired here: chat HTTP contracts are H4.3 (FR-025). The
registry, executor and topology v2 graph are composed over real application
services so the harness and integration tests exercise the real tool surface.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from umbral.agent.graph import TOOLS_TOPOLOGY_VERSION, build_topology_v2
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import TOOLS_STATE_SCHEMA_VERSION
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.ports import ModelGateway, RunRecorder
from umbral.application.agent.tools.ports import SessionScope, SessionScopeReader
from umbral.application.chat.contracts import ChatSessionNotFound
from umbral.application.chat.ports import ConversationGateway
from umbral.application.chat.service import ChatService
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract

Clock = Callable[[], datetime]


class ChatScopeReader:
    """Resolves a session's scope through the chat service (ownership-scoped)."""

    def __init__(self, chat: ChatService) -> None:
        self.chat = chat

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        try:
            session = self.chat.get_session(user_id=user_id, session_id=session_id)
        except ChatSessionNotFound:
            return None
        if session.search_profile_id is None:
            return None
        return SessionScope(
            session_id=session.session_id,
            search_profile_id=session.search_profile_id,
            status=session.status,
        )


def chat_scope_reader(chat: ChatService) -> SessionScopeReader:
    return ChatScopeReader(chat)


def build_tool_registry() -> ToolRegistry:
    return ToolRegistry(load_tool_contract)


def build_tool_executor(
    *,
    services: ToolServices,
    recorder: RunRecorder,
    chat: ChatService,
    timeout_seconds: float = 10.0,
    output_max_items: int = 20,
) -> ToolExecutor:
    return ToolExecutor(
        registry=build_tool_registry(),
        implementations=build_tool_implementations(services),
        recorder=recorder,
        scope_reader=chat_scope_reader(chat),
        timeout_seconds=timeout_seconds,
        output_max_items=output_max_items,
    )


def build_agent_stack_v2(
    *,
    gateway: ModelGateway,
    conversation: ConversationGateway,
    recorder: RunRecorder,
    saver: object,
    tool_executor: ToolExecutor,
    clock: Clock,
    model_version: str,
    prompt_version: str,
    schema_version: str,
    reply_schema: dict[str, object],
    max_calls_per_turn: int = 5,
    runs: object | None = None,
) -> ChatRuntime:
    graph = build_topology_v2(
        gateway=gateway,
        conversation=conversation,
        recorder=recorder,
        saver=saver,
        tool_executor=tool_executor,
        clock=clock,
        model_version=model_version,
        prompt_version=prompt_version,
        schema_version=schema_version,
        reply_schema=reply_schema,
        max_calls_per_turn=max_calls_per_turn,
    )
    return ChatRuntime(
        graph=graph,
        conversation=conversation,
        runs=runs,  # type: ignore[arg-type]
        recorder=recorder,
        clock=clock,
        state_schema_version=TOOLS_STATE_SCHEMA_VERSION,
        topology_version=TOOLS_TOPOLOGY_VERSION,
    )
