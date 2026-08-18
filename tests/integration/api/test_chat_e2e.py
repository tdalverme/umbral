# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Production-composition E2E: the v3 stack over real Postgres (R-10, T062)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from itertools import count
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.integration.agent.conftest import (
    seed_profile,
    seed_user,
)
from tests.integration.agent.tools.conftest import build_scope_stack
from tests.support.containers import ServiceConnection
from tests.support.tools import FakeCriteria, FakeFeedback, FakeRadar, FakeScoring

from umbral.agent.graph import build_topology_v3
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import CHAT_STATE_SCHEMA_VERSION
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.service import RunRecorderService
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.infrastructure.agent.checkpointer import create_postgres_saver
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.agent.tools.preferences_loader import (
    load_preference_vocabulary,
)
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
    SqlAlchemyModelCallRepository,
    SqlAlchemyNodeRunRepository,
    SqlAlchemyProposalRepository,
)
from umbral.infrastructure.db.repositories.chat import (
    SqlAlchemyChatMessageRepository,
    SqlAlchemyChatSessionRepository,
    SqlAlchemySearchProfileStatusReader,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Session]


@pytest.fixture
def chat_backend(request: pytest.FixtureRequest) -> tuple[SessionFactory, str]:
    """Postgres at head for the chat E2E (mirrors the agent conftest fixture)."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory, connection.url

_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
_tick = count()

_REPLY_SCHEMA = {
    "reply_text": {"kind": "string"},
    "refs": {"kind": "list"},
    "tool_calls": {"kind": "list", "max_items": 5},
}


def _clock() -> datetime:
    return _NOW + timedelta(seconds=next(_tick))


class _NoopPreferenceGateway:
    """E2E chat tests never reach the preference gateway."""

    def get_proposal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")

    def confirm_proposal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")

    def confirm_preference_removal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")

    def reject_proposal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")


class _ScriptedGateway:
    def __init__(self) -> None:
        self.reply_index = 0

    def generate_structured(
        self,
        *,
        messages,
        schema,
        schema_version,
        prompt_version,
        model_version,
        tools=None,
    ):
        if prompt_version == "agent-intent-v1":
            content: Mapping[str, object] = {
                "intent": "refinamiento",
                "parameters": [
                    {"key": "budget", "value": "900", "confidence": 0.95}
                ],
                "high_impact_missing": [],
                "contradictions": [],
            }
        elif self.reply_index == 0:
            self.reply_index += 1
            content = {
                "reply_text": "Voy a proponer el cambio.",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "propose_search_profile_update",
                        "args": {"change": {"budget_max": 900}},
                    }
                ],
            }
        else:
            content = {"reply_text": "Apliqué el cambio.", "refs": [], "tool_calls": []}
        return ModelResult(
            content=dict(content),
            model_version="local-fake",
            status="success",
            latency_ms=1,
            input_tokens=8,
            output_tokens=16,
            total_tokens=24,
        )


def _build_runtime(factory, url: str) -> ChatRuntime:
    chat = ChatService(
        sessions=SqlAlchemyChatSessionRepository(factory),
        messages=SqlAlchemyChatMessageRepository(factory),
        profile_status=SqlAlchemySearchProfileStatusReader(factory),
        events_out=SqlAlchemyEventRepository(factory),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=_clock,
    )
    scope = build_scope_stack(factory)
    proposals = SearchProfileUpdateProposals(
        repository=SqlAlchemyProposalRepository(factory),
        radar=FakeRadar(),
        events=SqlAlchemyEventRepository(factory),
        events_registry=load_events_registry(),
        ttl_hours=24,
        clock=_clock,
    )
    runs = SqlAlchemyGraphRunRepository(factory)
    recorder = RunRecorderService(
        graph_runs=runs,
        node_runs=SqlAlchemyNodeRunRepository(factory),
        model_calls=SqlAlchemyModelCallRepository(factory),
    )
    executor = ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations=build_tool_implementations(
            ToolServices(
                radar=FakeRadar(),
                scoring=FakeScoring(),
                feedback=FakeFeedback(),
                criteria=FakeCriteria(),
                proposals=proposals,
                vocabulary=load_preference_vocabulary(),
            )
        ),
        recorder=recorder,
        scope_reader=scope.scope_reader,
        timeout_seconds=5.0,
    )
    gateway = _ScriptedGateway()
    compiler = IntentCompiler(
        gateway=gateway,
        contract=load_intent_contract(),
        prompt_version="agent-intent-v1",
        model_version="local-fake",
    )
    graph = build_topology_v3(
        gateway=gateway,
        conversation=chat,
        recorder=recorder,
        saver=create_postgres_saver(url, strict_msgpack=True),
        tool_executor=executor,
        intent_compiler=compiler,
        decision_gateway=proposals,
        preference_gateway=_NoopPreferenceGateway(),
        clock=_clock,
        model_version="local-fake",
        prompt_version="agent-reply-v2",
        schema_version="reply-v3",
        reply_schema=_REPLY_SCHEMA,
        max_calls_per_turn=5,
        high_impact_keys=("budget", "zona", "hard_filters", "radio"),
        clarification_min_confidence=0.6,
        clarification_max_rounds=2,
        reply_chunk_words=8,
        reply_max_refs=10,
    )
    return ChatRuntime(
        graph=graph,
        conversation=chat,
        runs=runs,
        recorder=recorder,
        clock=_clock,
        state_schema_version=CHAT_STATE_SCHEMA_VERSION,
        topology_version=3,
    )


@pytest.mark.integration
def test_e2e_propose_interrupt_and_decision_over_real_postgres(
    chat_backend: tuple[SessionFactory, str],
) -> None:
    factory, url = chat_backend
    runtime = _build_runtime(factory, url)
    owner_id = seed_user(factory)
    profile = seed_profile(factory, owner_id)
    chat = ChatService(
        sessions=SqlAlchemyChatSessionRepository(factory),
        messages=SqlAlchemyChatMessageRepository(factory),
        profile_status=SqlAlchemySearchProfileStatusReader(factory),
        events_out=SqlAlchemyEventRepository(factory),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=_clock,
    )
    session = chat.create_session(
        user_id=owner_id, search_profile_id=profile.profile_id, correlation_id=uuid4()
    )

    first = runtime.run_turn(
        user_id=owner_id,
        session_id=session.session_id,
        text="subí el presupuesto a 900",
        correlation_id=uuid4(),
    )
    assert first.status == "interrupted"
    assert first.interrupt is not None
    proposal_id = UUID(str(first.interrupt["proposal_id"]))

    # The proposal is durable in Postgres.
    repo = SqlAlchemyProposalRepository(factory)
    persisted = repo.get(proposal_id, session.session_id, owner_id)
    assert persisted is not None
    assert persisted.state == "pending"

    second = runtime.run_turn(
        user_id=owner_id,
        session_id=session.session_id,
        text="",
        correlation_id=uuid4(),
        resume=True,
        decision={"kind": "approve", "idempotency_key": "e2e-key"},
    )
    assert second.run_id == first.run_id
    assert second.status == "completed"
    approved = repo.get(proposal_id, session.session_id, owner_id)
    assert approved is not None and approved.state == "approved"
