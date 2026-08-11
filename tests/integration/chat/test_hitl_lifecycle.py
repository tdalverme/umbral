# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""HITL lifecycle through the real graph v3 + runtime (FR-011..FR-016, T024)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from tests.support.agent import InMemoryGraphRunRepository, RecordingRunRecorder
from tests.support.chat import RecordingConversation
from tests.support.tools import FakeRadar

from umbral.agent.graph import build_topology_v3
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import CHAT_STATE_SCHEMA_VERSION
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.contracts import Proposal
from umbral.application.agent.tools.ports import SessionScope
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.radar.contract_loader import load_events_registry

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
PROFILE_ID = UUID(int=5)
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

_REPLY_SCHEMA = {
    "reply_text": {"kind": "string"},
    "refs": {"kind": "list"},
    "tool_calls": {"kind": "list", "max_items": 5},
}


class _Repo:
    def __init__(self) -> None:
        self.proposals: dict[UUID, Proposal] = {}

    def insert(self, proposal: Proposal) -> Proposal:
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def get(self, proposal_id, session_id, user_id):
        return self.proposals.get(proposal_id)

    def latest_pending_for_profile(self, search_profile_id, session_id):
        return None

    def list_for_profile(self, search_profile_id, state):
        return tuple(
            p
            for p in self.proposals.values()
            if p.search_profile_id == search_profile_id and p.state == state
        )

    def mark_approved(self, proposal_id, key, *, profile_version=None, run_id=None):
        proposal = self.proposals[proposal_id]
        updated = replace(
            proposal,
            state="approved",
            applied_idempotency_key=key,
            applied_profile_version=profile_version,
            applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_rejected(self, proposal_id, reason, rejection_at, rejection_note=None):
        proposal = self.proposals[proposal_id]
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason=reason,
            rejection_note=rejection_note,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_superseded(self, proposal_id, superseded_by, rejection_at):
        proposal = self.proposals[proposal_id]
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason="edited",
            superseded_by_proposal_id=superseded_by,
        )
        self.proposals[proposal_id] = updated
        return updated

    def expire_pending(self, expired_before):
        return 0


class _ScopeReader:
    def __init__(self) -> None:
        self.scope = SessionScope(
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            status="active",
        )

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        return self.scope


class _ScriptedGateway:
    def __init__(self, reply_sequence: list[Mapping[str, object]]) -> None:
        self._sequence = reply_sequence
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
        self.calls.append({"prompt_version": prompt_version})
        if prompt_version == "agent-intent-v1":
            content: Mapping[str, object] = {
                "intent": "refinamiento",
                "parameters": [
                    {"key": "budget", "value": "900", "confidence": 0.95}
                ],
                "high_impact_missing": [],
                "contradictions": [],
            }
        else:
            content = self._sequence[min(len(self.calls) - 2, len(self._sequence) - 1)]
        return ModelResult(
            content=dict(content),
            model_version="local-fake",
            status="success",
            latency_ms=1,
            input_tokens=8,
            output_tokens=16,
            total_tokens=24,
        )


class _SessionConversation(RecordingConversation):
    def assert_accepts_turn(self, *, user_id, session_id):
        from umbral.application.chat.contracts import ChatSession

        self.accept_calls += 1
        return ChatSession(
            session_id=session_id,
            user_id=user_id,
            search_profile_id=PROFILE_ID,
            status="active",
            created_at=NOW,
            correlation_id=UUID(int=0),
        )


def _build() -> tuple[ChatRuntime, _Repo, _ScriptedGateway]:
    repo = _Repo()
    radar = FakeRadar()
    proposals = SearchProfileUpdateProposals(
        repository=repo,
        radar=radar,
        events=_Events(),
        events_registry=load_events_registry(),
        ttl_hours=24,
        clock=lambda: NOW,
    )
    recorder = RecordingRunRecorder()
    registry = ToolRegistry(load_tool_contract)
    executor = ToolExecutor(
        registry=registry,
        implementations=build_tool_implementations(
            ToolServices(
                radar=radar,
                scoring=FakeScoring(),
                feedback=FakeFeedback(),
                criteria=FakeCriteria(),
                proposals=proposals,
            )
        ),
        recorder=recorder,
        scope_reader=_ScopeReader(),
        timeout_seconds=1.0,
    )
    gateway = _ScriptedGateway(
        [
            {
                "reply_text": "Voy a proponer el cambio de presupuesto.",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "propose_search_profile_update",
                        "args": {"change": {"budget_max": 900}},
                    }
                ],
            },
            {
                "reply_text": "Tu radar ahora busca hasta 900.",
                "refs": [],
                "tool_calls": [],
            },
        ]
    )
    compiler = IntentCompiler(
        gateway=gateway,
        contract=load_intent_contract(),
        prompt_version="agent-intent-v1",
        model_version="local-fake",
    )
    graph = build_topology_v3(
        gateway=gateway,
        conversation=_SessionConversation(),
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=executor,
        intent_compiler=compiler,
        decision_gateway=proposals,
        clock=lambda: NOW,
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
    runtime = ChatRuntime(
        graph=graph,  # type: ignore[arg-type]
        conversation=_SessionConversation(),
        runs=InMemoryGraphRunRepository(),
        recorder=recorder,
        clock=lambda: NOW,
        state_schema_version=CHAT_STATE_SCHEMA_VERSION,
        topology_version=3,
    )
    return runtime, repo, gateway


def test_propose_interrupts_and_approve_resumes_same_run() -> None:
    runtime, repo, _gateway = _build()
    events: list[object] = []
    first = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="subÃ­ el presupuesto a 900",
        correlation_id=UUID(int=40),
        consumer=events.append,
    )
    assert first.status == "interrupted"
    assert first.interrupt is not None
    first_interrupt = first.interrupt
    assert first_interrupt["type"] == "proposal_decision"
    proposal_id = UUID(str(first_interrupt["proposal_id"]))
    proposal = repo.proposals[proposal_id]
    assert proposal.state == "pending"

    second = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "approve", "idempotency_key": "decision-1"},
        consumer=events.append,
    )
    assert second.run_id == first.run_id
    assert second.status == "completed"
    assert repo.proposals[proposal_id].state == "approved"


def test_propose_and_interactive_reject_marks_user() -> None:
    runtime, repo, _gateway = _build()
    first = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="subÃ­ el presupuesto a 900",
        correlation_id=UUID(int=40),
    )
    assert first.interrupt is not None
    proposal_id = UUID(str(first.interrupt["proposal_id"]))
    second = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "reject", "reason": "no me convence"},
    )
    assert second.status == "completed"
    rejected = repo.proposals[proposal_id]
    assert rejected.state == "rejected"
    assert rejected.rejection_reason == "user"
    assert rejected.rejection_note == "no me convence"


def test_edit_derives_new_proposal_and_waits_again() -> None:
    runtime, repo, _gateway = _build()
    first = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="subÃ­ el presupuesto a 900",
        correlation_id=UUID(int=40),
    )
    assert first.interrupt is not None
    original_id = UUID(str(first.interrupt["proposal_id"]))
    second = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "edit", "change": {"budget_max": 1100}},
    )
    # The derived proposal waits for a fresh confirmation (second interrupt).
    assert second.status == "interrupted"
    assert second.interrupt is not None
    second_interrupt = second.interrupt
    derived_id = UUID(str(second_interrupt["proposal_id"]))
    assert derived_id != original_id
    assert repo.proposals[original_id].state == "rejected"
    assert repo.proposals[original_id].rejection_reason == "edited"
    assert repo.proposals[original_id].superseded_by_proposal_id == derived_id
    assert repo.proposals[derived_id].state == "pending"
    assert repo.proposals[derived_id].diff == {"budget_max": 1100}

    third = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=42),
        resume=True,
        decision={"kind": "approve", "idempotency_key": "decision-2"},
    )
    assert third.status == "completed"
    assert repo.proposals[derived_id].state == "approved"


class _Events:
    def __init__(self) -> None:
        self.events: list[object] = []

    def insert(self, event: object) -> None:
        self.events.append(event)


from tests.support.tools import (  # noqa: E402
    FakeCriteria,
    FakeFeedback,
    FakeScoring,
)
