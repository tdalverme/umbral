# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Bounded tool loop over the real checkpointer (R-14, T045)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import uuid4

from tests.integration.agent.conftest import seed_profile, seed_user
from tests.integration.agent.tools.conftest import build_scope_stack
from tests.integration.chat.conftest import build_chat

from umbral.agent.graph import build_topology_v2
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import TOOLS_STATE_SCHEMA_VERSION
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.service import RunRecorderService
from umbral.infrastructure.agent.checkpointer import create_postgres_saver
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
    SqlAlchemyModelCallRepository,
    SqlAlchemyNodeRunRepository,
)

REPLY_SCHEMA = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "refs": {"kind": "list"},
    "tool_calls": {"kind": "list", "max_items": 5},
}


class _ScriptedGateway:
    def __init__(self, replies: list[Mapping[str, object]]) -> None:
        self._replies = replies
        self.calls: list[Mapping[str, object]] = []

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ModelResult:
        self.calls.append({"schema_version": schema_version})
        reply = self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]
        return ModelResult(
            content=dict(reply),
            model_version="local-fake",
            status="success",
            latency_ms=1,
            input_tokens=8,
            output_tokens=16,
            total_tokens=24,
        )


def test_graph_tool_loop_records_tool_runs(agent_backend) -> None:
    factory, url = agent_backend
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    chat = build_chat(factory)
    session = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    scope = build_scope_stack(factory)

    runs = SqlAlchemyGraphRunRepository(factory)
    recorder = RunRecorderService(
        graph_runs=runs,
        node_runs=SqlAlchemyNodeRunRepository(factory),
        model_calls=SqlAlchemyModelCallRepository(factory),
    )

    def find_matches(_ctx, _args):
        return {"run_id": None, "items": [], "total": 0, "stale": True}

    executor = ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations={"find_matches": find_matches},
        recorder=recorder,
        scope_reader=scope.scope_reader,
        timeout_seconds=10.0,
    )
    gateway = _ScriptedGateway(
        [
            {
                "reply_text": "busco",
                "refs": [],
                "tool_calls": [
                    {"tool": "find_matches", "args": {"page": 1, "limit": 5}}
                ],
            },
            {"reply_text": "no hay resultados", "refs": [], "tool_calls": []},
        ]
    )
    saver = create_postgres_saver(url, strict_msgpack=True)
    graph = build_topology_v2(
        gateway=gateway,
        conversation=scope.chat,
        recorder=recorder,
        saver=saver,
        tool_executor=executor,
        clock=scope.chat.clock,
        model_version="local-fake",
        prompt_version="agent-tools-v1",
        schema_version="reply-v2",
        reply_schema=REPLY_SCHEMA,
        max_calls_per_turn=5,
    )
    runtime = ChatRuntime(
        graph=graph,
        conversation=scope.chat,
        runs=runs,
        recorder=recorder,
        clock=scope.chat.clock,
        state_schema_version=TOOLS_STATE_SCHEMA_VERSION,
    )
    outcome = runtime.run_turn(
        user_id=user_id,
        session_id=session.session_id,
        text="mostrame matches",
        correlation_id=uuid4(),
    )
    assert outcome.status == "completed"

    from sqlalchemy import select

    from umbral.infrastructure.db.models.agent import AgentNodeRun

    with factory() as session:
        tool_runs = session.scalars(
            select(AgentNodeRun).where(AgentNodeRun.node_kind == "tool")
        ).all()
    assert len(tool_runs) == 1
    assert tool_runs[0].node_name == "find_matches"
    assert len(gateway.calls) == 2
