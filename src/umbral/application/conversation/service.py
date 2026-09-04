"""Ordered V5 turn orchestration with confirmation and idempotency.

Processing follows the design's multi-act semantics: resolve the active pending
action first, reload context after that state-changing segment, re-plan the
remaining typed acts against the refreshed context, execute safe acts in
expressed order, and stop the affected segment at a pending or clarification
decision. Later acts whose prerequisites were not met are marked
``not_executed``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.conversation.contracts import (
    ActDecision,
    ActOutcome,
    Command,
    ConversationAct,
    ConversationTurnResult,
    ExecutedAct,
    FailureStage,
    ResolvePending,
    TurnContext,
    TurnInterpretation,
    TurnPlan,
)
from umbral.application.conversation.ports import (
    ContextReader,
    EffectExecutorLike,
    Interpreter,
    PendingResolver,
    TurnAuditWriter,
    TurnPolicy,
)
from umbral.application.conversation.receipts import (
    CommandReceiptStore,
    execute_with_receipt,
)


class ConversationTurn:
    """Executes one full V5 turn through its explicit ports."""

    def __init__(
        self,
        *,
        contexts: ContextReader,
        interpreter: Interpreter,
        policy: TurnPolicy,
        executor: EffectExecutorLike,
        pending: PendingResolver,
        receipts: CommandReceiptStore,
        audit: TurnAuditWriter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.contexts = contexts
        self.interpreter = interpreter
        self.policy = policy
        self.executor = executor
        self.pending = pending
        self.receipts = receipts
        self.audit = audit
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load_context(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> TurnContext:
        return self.contexts.load(
            user_id=user_id, session_id=session_id, correlation_id=correlation_id
        )

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContext,
        correlation_id: UUID,
    ) -> TurnInterpretation:
        return self.interpreter.interpret(
            message_text=message_text,
            context=context,
            correlation_id=correlation_id,
        )

    def plan(
        self,
        *,
        user_message: str,
        context: TurnContext,
        interpretation: TurnInterpretation,
    ) -> TurnPlan:
        return self.policy(
            user_message=user_message,
            context=context,
            interpretation=interpretation,
        )

    def resolve_pending(
        self,
        *,
        act_id: str,
        context: TurnContext,
        pending_ref: str,
        decision: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutedAct:
        """Resolve exactly the context-authorized queue head."""
        return self.pending.resolve(
            act_id=act_id,
            context=context,
            pending_ref=pending_ref,
            decision=decision,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )

    def process(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        message_id: UUID,
        message_text: str,
        correlation_id: UUID,
    ) -> ConversationTurnResult:
        context = self.load_context(
            user_id=user_id, session_id=session_id, correlation_id=correlation_id
        )
        try:
            interpretation = self.interpret(
                message_text=message_text,
                context=context,
                correlation_id=correlation_id,
            )
        except Exception as error:
            stage: FailureStage = (
                "provider_failure"
                if _is_provider_error(error)
                else "interpretation_failure"
            )
            return self._failed_result(context, stage)
        try:
            plan = self.plan(
                user_message=message_text,
                context=context,
                interpretation=interpretation,
            )
        except Exception:
            return self._failed_result(context, "policy_failure")
        return self.execute(
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            message_text=message_text,
            correlation_id=correlation_id,
            context=context,
            interpretation=interpretation,
            plan=plan,
        )

    def execute(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        message_id: UUID,
        message_text: str,
        correlation_id: UUID,
        context: TurnContext,
        interpretation: TurnInterpretation,
        plan: TurnPlan,
    ) -> ConversationTurnResult:
        executed: list[ExecutedAct] = []
        outcomes: list[ActOutcome] = []
        try:
            context, acts, decisions, commands_by_act = self._pending_segment(
                context=context,
                interpretation=interpretation,
                acts=list(interpretation.acts),
                plan=plan,
                user_id=user_id,
                session_id=session_id,
                message_id=message_id,
                message_text=message_text,
                correlation_id=correlation_id,
                executed=executed,
                outcomes=outcomes,
            )

            for act in sorted(acts, key=_execution_priority):
                act_id = act.act_id
                if any(outcome.act_id == act_id for outcome in outcomes):
                    continue
                decision = decisions.get(act_id)
                if decision is None:
                    outcomes.append(ActOutcome(act_id, "not_executed"))
                    continue
                if decision.status == "rejected":
                    outcomes.append(
                        ActOutcome(act_id, "rejected", decision.reason_code)
                    )
                    continue
                if decision.status == "needs_clarification":
                    outcomes.append(
                        ActOutcome(
                            act_id, "needs_clarification", decision.reason_code
                        )
                    )
                    break
                command = commands_by_act.get(act_id)
                if command is None:
                    outcomes.append(
                        ActOutcome(
                            act_id,
                            "pending" if decision.status == "pending" else "applied",
                            decision.reason_code,
                        )
                    )
                    continue
                key = self._idempotency_key(session_id, message_id, act_id)
                result = execute_with_receipt(
                    store=self.receipts,
                    executor=self.executor,
                    command=command,
                    context=context,
                    idempotency_key=key,
                    correlation_id=correlation_id,
                )
                executed.append(result)
                outcomes.append(self._outcome_for(result))
                if result.status == "needs_clarification":
                    break

            for act in acts:
                if not any(outcome.act_id == act.act_id for outcome in outcomes):
                    outcomes.append(ActOutcome(act.act_id, "not_executed"))
        except Exception:
            return self._failed_result(context, "execution_failure")

        if any(result.status == "pending" for result in executed):
            context = self.contexts.load(
                user_id=user_id, session_id=session_id, correlation_id=correlation_id
            )
        turn_result = ConversationTurnResult(
            context=context,
            interpretation=interpretation,
            plan=plan,
            executed=tuple(executed),
            outcomes=_outcomes_in_act_order(interpretation.acts, outcomes),
        )
        return self._record_audit(turn_result, interpretation)

    def _pending_segment(
        self,
        *,
        context: TurnContext,
        interpretation: TurnInterpretation,
        acts: list[ConversationAct],
        plan: TurnPlan,
        user_id: UUID,
        session_id: UUID,
        message_id: UUID,
        message_text: str,
        correlation_id: UUID,
        executed: list[ExecutedAct],
        outcomes: list[ActOutcome],
    ) -> tuple[
        TurnContext,
        list[ConversationAct],
        dict[str, ActDecision],
        dict[str, Command],
    ]:
        if not acts or not isinstance(acts[0], ResolvePending):
            return context, acts, _decision_map(plan), _commands_by_act(plan)
        act = acts[0]
        key = self._idempotency_key(session_id, message_id, act.act_id)
        result = self.pending.resolve(
            act_id=act.act_id,
            context=context,
            pending_ref=act.pending_ref,
            decision=act.decision,
            correlation_id=correlation_id,
            idempotency_key=key,
        )
        executed.append(result)
        outcomes.append(self._outcome_for(result))
        context = self.contexts.load(
            user_id=user_id, session_id=session_id, correlation_id=correlation_id
        )
        remaining = acts[1:]
        if not remaining:
            return context, [], {}, {}
        replanned = self.policy(
            user_message=message_text,
            context=context,
            interpretation=TurnInterpretation(
                model_version=interpretation.model_version,
                prompt_version=interpretation.prompt_version,
                acts=tuple(remaining),
            ),
        )
        return (
            context,
            remaining,
            _decision_map(replanned),
            _commands_by_act(replanned),
        )

    def _outcome_for(self, result: ExecutedAct) -> ActOutcome:
        if result.status == "applied":
            return ActOutcome(
                result.act_id, "applied", result.reason_code, result.object_ref
            )
        if result.status == "pending":
            return ActOutcome(
                result.act_id, "pending", result.reason_code, result.object_ref
            )
        if result.reason_code == "execution.stale_context":
            return ActOutcome(
                result.act_id,
                "needs_clarification",
                result.reason_code,
                result.object_ref,
            )
        return ActOutcome(
            result.act_id, "rejected", result.reason_code, result.object_ref
        )

    def _idempotency_key(
        self, session_id: UUID, message_id: UUID, act_id: str
    ) -> str:
        return f"conversation:{session_id}:{message_id}:{act_id}"

    def _failed_result(
        self, context: TurnContext, failure_stage: FailureStage
    ) -> ConversationTurnResult:
        return ConversationTurnResult(
            context=context,
            interpretation=None,
            plan=None,
            executed=(),
            outcomes=(),
            failure_stage=failure_stage,
        )

    def _record_audit(
        self,
        result: ConversationTurnResult,
        interpretation: TurnInterpretation,
    ) -> ConversationTurnResult:
        if self.audit is None:
            return result
        versions: Mapping[str, object] = {
            "contract_version": "5",
            "interpretation_version": interpretation.interpretation_version,
            "model_version": interpretation.model_version,
            "prompt_version": interpretation.prompt_version,
        }
        try:
            self.audit.record(result, versions)
        except Exception:
            return ConversationTurnResult(
                context=result.context,
                interpretation=result.interpretation,
                plan=result.plan,
                executed=result.executed,
                outcomes=result.outcomes,
                failure_stage="contract_or_fixture_failure",
            )
        return result


def _decision_map(plan: TurnPlan) -> dict[str, ActDecision]:
    return {decision.act_id: decision for decision in plan.decisions}


def _commands_by_act(plan: TurnPlan) -> dict[str, Command]:
    return {command.act_id: command for command in plan.commands}


def _execution_priority(act: ConversationAct) -> int:
    """Persist soft desires before creating every hard-filter proposal."""
    if act.kind in {"express_desire", "revise_desire", "withdraw_desire"}:
        return 0
    if act.kind in {"set_filter", "clear_filter"}:
        return 1
    return 2


def _outcomes_in_act_order(
    acts: tuple[ConversationAct, ...], outcomes: list[ActOutcome]
) -> tuple[ActOutcome, ...]:
    by_act = {outcome.act_id: outcome for outcome in outcomes}
    return tuple(by_act[act.act_id] for act in acts if act.act_id in by_act)


def _is_provider_error(error: Exception) -> bool:
    from umbral.agent.intent import InterpretationContractFailed

    return isinstance(error, InterpretationContractFailed) and (
        error.reason == "provider_failure" or error.reason.startswith("provider")
    )
