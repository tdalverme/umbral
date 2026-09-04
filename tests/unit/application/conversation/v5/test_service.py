"""Unit tests for V5 ordered turn orchestration."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from umbral.agent.intent.v5 import InterpretationContractFailed
from umbral.application.conversation.v5.contracts import (
    ConversationActV5,
    EvidenceSpan,
    ExecutedActV5,
    ExpressDesire,
    HardFilterV5,
    PendingActionV5,
    RecordDesireCommand,
    ResolvePending,
    SetFilter,
    SetFilterCommand,
    TurnContextV5,
    TurnInterpretationV5,
)
from umbral.application.conversation.v5.policy import plan_turn_v5
from umbral.application.conversation.v5.receipts import (
    InMemoryCommandReceiptStore,
)
from umbral.application.conversation.v5.service import ConversationTurnV5

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
MESSAGE_ID = UUID(int=3)
CORRELATION_ID = UUID(int=4)

_ALL_CAPABILITIES = (
    "create_radar",
    "set_filter",
    "clear_filter",
    "express_desire",
    "revise_desire",
    "withdraw_desire",
    "record_feedback",
    "resolve_pending",
    "query",
    "unsupported_request",
)


class _FakeContexts:
    def __init__(self, context: TurnContextV5) -> None:
        self.context = context
        self.load_calls = 0

    def load(
        self, *, user_id: UUID, session_id: UUID, correlation_id: UUID
    ) -> TurnContextV5:
        self.load_calls += 1
        return self.context


class _FakeInterpreter:
    def __init__(
        self,
        interpretation: TurnInterpretationV5 | None = None,
        error: Exception | None = None,
    ) -> None:
        self.interpretation = interpretation
        self.error = error

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContextV5,
        correlation_id: object | None = None,
    ) -> TurnInterpretationV5:
        if self.error is not None:
            raise self.error
        assert self.interpretation is not None
        return self.interpretation


class _FakeExecutor:
    def __init__(self, results: dict[str, ExecutedActV5] | None = None) -> None:
        self.results = results or {}
        self.calls: list[str] = []

    def execute(
        self,
        *,
        command: Any,
        context: TurnContextV5,
        idempotency_key: str,
    ) -> ExecutedActV5:
        self.calls.append(command.act_id)
        configured = self.results.get(command.act_id)
        if configured is not None:
            return configured
        if isinstance(command, RecordDesireCommand):
            return ExecutedActV5(
                command.act_id,
                "desire.remembered",
                object_ref=f"desire:{uuid4()}",
            )
        if isinstance(command, SetFilterCommand):
            return ExecutedActV5(
                command.act_id,
                "filter.set",
                status="pending",
                object_ref=f"proposal:{uuid4()}",
                reason_code="filter.changes_existing_hard_filter",
            )
        return ExecutedActV5(command.act_id, "command.executed")


class _FakePending:
    def __init__(self, result: ExecutedActV5) -> None:
        self.result = result
        self.calls = 0

    def resolve(
        self,
        *,
        act_id: str,
        context: TurnContextV5,
        pending_ref: str,
        decision: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutedActV5:
        self.calls += 1
        return self.result


def _context(
    *,
    filters: tuple[HardFilterV5, ...] = (),
    pending_ref: str | None = None,
) -> TurnContextV5:
    return TurnContextV5(
        user_id=str(USER_ID),
        session_id=str(SESSION_ID),
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=filters,
        active_desires=(),
        pending_action=(
            PendingActionV5(pending_ref=pending_ref) if pending_ref else None
        ),
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=_ALL_CAPABILITIES,
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=str(CORRELATION_ID),
    )


def _interpretation(*acts: ConversationActV5) -> TurnInterpretationV5:
    return TurnInterpretationV5(
        model_version="gpt-4.1-mini",
        prompt_version="interpretation-v5",
        acts=acts,
    )


def _span(message: str, text: str) -> EvidenceSpan:
    start = message.index(text)
    return EvidenceSpan(start=start, end=start + len(text), text=text)


def _service(
    *,
    context: TurnContextV5,
    interpretation: TurnInterpretationV5 | None = None,
    executor: _FakeExecutor | None = None,
    pending_result: ExecutedActV5 | None = None,
    interpreter_error: Exception | None = None,
    receipts: InMemoryCommandReceiptStore | None = None,
) -> tuple[ConversationTurnV5, _FakeContexts, _FakeExecutor, _FakePending]:
    contexts = _FakeContexts(context)
    interpreter = _FakeInterpreter(interpretation, interpreter_error)
    executor = executor or _FakeExecutor()
    pending = _FakePending(
        pending_result
        or ExecutedActV5("a1", "pending.resolved", object_ref="radar:1")
    )
    service = ConversationTurnV5(
        contexts=contexts,
        interpreter=interpreter,
        policy=plan_turn_v5,
        executor=executor,
        pending=pending,
        receipts=receipts or InMemoryCommandReceiptStore(),
    )
    return service, contexts, executor, pending


def test_confirm_then_add_balcony_reloads_context_and_executes_both_segments() -> None:
    message = "Sí, confirmo, y también quiero balcón"
    context = _context(pending_ref="pending:1")
    interpretation = _interpretation(
        ResolvePending(
            act_id="a1",
            confidence=0.9,
            evidence_spans=(_span(message, "confirmo"),),
            pending_ref="pending:1",
            decision="approve",
        ),
        ExpressDesire(
            act_id="a2",
            confidence=0.9,
            evidence_spans=(_span(message, "quiero balcón"),),
            raw_text="quiero balcón",
            subject_ref="balcon",
        ),
    )
    service, contexts, _, _ = _service(
        context=context, interpretation=interpretation
    )

    result = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text=message,
        correlation_id=CORRELATION_ID,
    )

    assert [item.effect_key for item in result.executed] == [
        "pending.resolved",
        "desire.remembered",
    ]
    assert contexts.load_calls == 2
    assert result.outcomes[0].status == "applied"
    assert result.outcomes[1].status == "applied"


def test_pending_filter_does_not_block_later_authorized_soft_desires() -> None:
    message = "Quiero balcón y subí el presupuesto a 1200"
    context = _context(
        filters=(HardFilterV5(filter_key="budget_max", value=800.0),)
    )
    interpretation = _interpretation(
        ExpressDesire(
            act_id="a1",
            confidence=0.9,
            evidence_spans=(_span(message, "Quiero balcón"),),
            raw_text="Quiero balcón",
            subject_ref="balcon",
        ),
        SetFilter(
            act_id="a2",
            confidence=0.9,
            evidence_spans=(_span(message, "subí el presupuesto a 1200"),),
            filter_key="budget_max",
            value=1200,
        ),
        ExpressDesire(
            act_id="a3",
            confidence=0.9,
            evidence_spans=(_span(message, "balcón"),),
            raw_text="balcón",
            subject_ref="balcon",
        ),
    )
    service, contexts, executor, _ = _service(
        context=context, interpretation=interpretation
    )

    result = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text=message,
        correlation_id=CORRELATION_ID,
    )

    assert result.outcomes[0].status == "applied"
    assert result.outcomes[1].status == "pending"
    assert result.outcomes[2].status == "applied"
    assert contexts.load_calls == 1


def test_soft_desires_execute_before_all_hard_filter_proposals() -> None:
    message = "Palermo, hasta 1200 y quiero mucha luz"
    context = _context()
    interpretation = _interpretation(
        SetFilter(
            act_id="zones", confidence=0.9,
            evidence_spans=(_span(message, "Palermo"),),
            filter_key="zones", value=("palermo",),
        ),
        ExpressDesire(
            act_id="light", confidence=0.9,
            evidence_spans=(_span(message, "mucha luz"),),
            raw_text="mucha luz", subject_ref="luminosidad",
        ),
        SetFilter(
            act_id="budget", confidence=0.9,
            evidence_spans=(_span(message, "hasta 1200"),),
            filter_key="budget_max", value=1200,
        ),
    )
    service, _, executor, _ = _service(context=context, interpretation=interpretation)

    result = service.process(
        user_id=USER_ID, session_id=SESSION_ID, message_id=MESSAGE_ID,
        message_text=message, correlation_id=CORRELATION_ID,
    )

    assert executor.calls == ["light", "zones", "budget"]
    assert [(item.act_id, item.status) for item in result.outcomes] == [
        ("zones", "pending"), ("light", "applied"), ("budget", "pending"),
    ]


def test_provider_failure_executes_nothing() -> None:
    service, _, executor, _ = _service(
        context=_context(),
        interpreter_error=InterpretationContractFailed("provider_failure"),
    )

    result = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text="hola",
        correlation_id=CORRELATION_ID,
    )

    assert result.failure_stage == "provider_failure"
    assert result.executed == ()
    assert result.outcomes == ()


def test_retries_reuse_idempotency_keys() -> None:
    message = "Quiero balcón"
    context = _context()
    interpretation = _interpretation(
        ExpressDesire(
            act_id="a1",
            confidence=0.9,
            evidence_spans=(_span(message, "Quiero balcón"),),
            raw_text="Quiero balcón",
            subject_ref="balcon",
        )
    )
    receipts = InMemoryCommandReceiptStore()
    service, _, executor, _ = _service(
        context=context,
        interpretation=interpretation,
        receipts=receipts,
    )

    first = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text=message,
        correlation_id=CORRELATION_ID,
    )
    second = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text=message,
        correlation_id=CORRELATION_ID,
    )

    assert first.outcomes[0].status == "applied"
    assert second.outcomes[0].status == "applied"
    assert executor.calls == ["a1"]


def test_stale_context_execution_returns_clarification() -> None:
    message = "Subí el presupuesto a 1200"
    context = _context()
    interpretation = _interpretation(
        SetFilter(
            act_id="a1",
            confidence=0.9,
            evidence_spans=(_span(message, "Subí el presupuesto a 1200"),),
            filter_key="budget_max",
            value=1200,
        )
    )
    stale = ExecutedActV5(
        act_id="a1",
        effect_key="filter.set",
        status="rejected",
        reason_code="execution.stale_context",
    )
    service, _, _, _ = _service(
        context=context,
        interpretation=interpretation,
        executor=_FakeExecutor(results={"a1": stale}),
    )

    result = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text=message,
        correlation_id=CORRELATION_ID,
    )

    assert result.outcomes[0].status == "needs_clarification"
    assert result.outcomes[0].reason_code == "execution.stale_context"
    assert result.failure_stage is None


def test_interpretation_contract_failure_is_attributed() -> None:
    service, _, _, _ = _service(
        context=_context(),
        interpreter_error=InterpretationContractFailed("duplicate act_id"),
    )

    result = service.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text="hola",
        correlation_id=CORRELATION_ID,
    )

    assert result.failure_stage == "interpretation_failure"
    assert result.executed == ()
