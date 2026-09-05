"""Separate V5 conversation graph topology (load/plan/execute/reply/persist).

The graph is a thin routing shell over the V5 turn module: its nodes call the
turn service phases and the reply composer; no policy, execution, or ranking
logic lives inside graph nodes. State is JSON-serializable under
``state-schema.json``.
"""
# mypy: disable-error-code="arg-type,index,call-overload,assignment"

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, TypedDict, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from umbral.application.conversation.contracts import (
    ActDecision,
    ActOutcome,
    ClearFilter,
    ClearFilterCommand,
    Command,
    ConceptLink,
    ConversationAct,
    ConversationTurnResult,
    CreateRadar,
    CreateRadarCommand,
    DesireView,
    EvidenceSpan,
    ExecutedAct,
    ExpressDesire,
    FocusedEntity,
    HardFilter,
    PendingAction,
    Query,
    RecordDesireCommand,
    RecordFeedback,
    RecordFeedbackCommand,
    ResolvePending,
    ReviseDesire,
    ReviseDesireCommand,
    SetFilter,
    SetFilterCommand,
    TurnContext,
    TurnInterpretation,
    TurnPlan,
    UnsupportedRequest,
    UntrustedContent,
    WithdrawDesire,
    WithdrawDesireCommand,
)
from umbral.application.conversation.reply import Reply


class ConversationGraphState(TypedDict, total=False):
    """Serializable graph state matching ``state-schema.json``."""

    contract_version: Literal["5"]
    schema_version: Literal["conversation-state"]
    message_id: str
    message_text: str
    context: dict[str, object] | None
    interpretation: dict[str, object] | None
    plan: dict[str, object] | None
    executed: list[dict[str, object]]
    outcomes: list[dict[str, object]]
    reply: dict[str, object] | None
    failure_stage: str | None
    confirmation_payload: dict[str, object] | None


class TurnServiceLike(Protocol):
    def load_context(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> TurnContext: ...

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContext,
        correlation_id: UUID,
    ) -> TurnInterpretation: ...

    def plan(
        self,
        *,
        user_message: str,
        context: TurnContext,
        interpretation: TurnInterpretation,
    ) -> TurnPlan: ...

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
    ) -> ConversationTurnResult: ...

    def resolve_pending(
        self,
        *,
        act_id: str,
        context: TurnContext,
        pending_ref: str,
        decision: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutedAct: ...


class ReplyComposerLike(Protocol):
    def compose(self, result: ConversationTurnResult) -> Reply: ...


@dataclass(frozen=True, slots=True)
class GraphDeps:
    turn: TurnServiceLike
    reply: ReplyComposerLike


@dataclass(frozen=True, slots=True)
class AgentGraph:
    """The single compiled semantic conversation graph plus its dependencies."""

    compiled: Any
    deps: GraphDeps


def build_graph(
    *,
    dependencies: GraphDeps,
    checkpointer: object | None = None,
) -> AgentGraph:
    """Build the single compiled graph matching ``graph-topology.json``."""
    deps = dependencies

    def _ids(config: Mapping[str, object]) -> dict[str, UUID]:
        configurable = cast(Mapping[str, object], config.get("configurable") or {})
        return {
            "user_id": UUID(str(configurable["user_id"])),
            "session_id": UUID(str(configurable["session_id"])),
            "correlation_id": UUID(str(configurable["correlation_id"])),
        }

    def _load_context(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        ids = _ids(config)
        context = deps.turn.load_context(
            user_id=ids["user_id"],
            session_id=ids["session_id"],
            correlation_id=ids["correlation_id"],
        )
        return {"context": _context_to_dict(context)}

    def _interpret_turn(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        context = _context_from_dict(state.get("context") or {})
        ids = _ids(config)
        try:
            interpretation = deps.turn.interpret(
                message_text=state["message_text"],
                context=context,
                correlation_id=ids["correlation_id"],
            )
        except Exception as error:
            return {
                "interpretation": None,
                "failure_stage": (
                    "provider_failure"
                    if _is_provider_error(error)
                    else "interpretation_failure"
                ),
            }
        return {"interpretation": _interpretation_to_dict(interpretation)}

    def _plan_segment(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        context = _context_from_dict(state.get("context") or {})
        interpretation = _interpretation_from_dict(
            state.get("interpretation") or {}
        )
        try:
            plan = deps.turn.plan(
                user_message=state["message_text"],
                context=context,
                interpretation=interpretation,
            )
        except Exception:
            return {"plan": None, "failure_stage": "policy_failure"}
        return {"plan": _plan_to_dict(plan)}

    def _execute_segment(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        if state.get("failure_stage") is not None:
            return {
                "executed": [],
                "outcomes": [],
                "interpretation": None,
                "plan": None,
            }
        ids = _ids(config)
        context = _context_from_dict(state.get("context") or {})
        interpretation = _interpretation_from_dict(
            state.get("interpretation") or {}
        )
        plan = _plan_from_dict(state.get("plan") or {})
        result = deps.turn.execute(
            user_id=ids["user_id"],
            session_id=ids["session_id"],
            message_id=UUID(state["message_id"]),
            message_text=state["message_text"],
            correlation_id=ids["correlation_id"],
            context=context,
            interpretation=interpretation,
            plan=plan,
        )
        context_after_execution = result.context
        if any(outcome.status == "pending" for outcome in result.outcomes):
            context_after_execution = deps.turn.load_context(
                user_id=ids["user_id"],
                session_id=ids["session_id"],
                correlation_id=ids["correlation_id"],
            )
        return {
            "context": _context_to_dict(context_after_execution),
            "interpretation": (
                _interpretation_to_dict(result.interpretation)
                if result.interpretation is not None
                else None
            ),
            "plan": _plan_to_dict(result.plan) if result.plan is not None else None,
            "executed": [_executed_to_dict(item) for item in result.executed],
            "outcomes": [_outcome_to_dict(item) for item in result.outcomes],
            "failure_stage": result.failure_stage,
        }

    def _reload_context(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        ids = _ids(config)
        context = deps.turn.load_context(
            user_id=ids["user_id"],
            session_id=ids["session_id"],
            correlation_id=ids["correlation_id"],
        )
        return {"context": _context_to_dict(context)}

    def _require_confirmation(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        context = _context_from_dict(state.get("context") or {})
        pending = context.pending_action
        if pending is None:
            return {}
        payload: dict[str, object] = {
            "type": "conversation_confirmation",
            "pending_ref": pending.pending_ref,
            "act_id": pending.act_id,
            "ordinal": pending.ordinal,
            "total": pending.total,
        }
        decision = interrupt(payload)
        return {"confirmation_payload": {"decision": decision}}

    def _resolve_pending(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        context = _context_from_dict(state.get("context") or {})
        pending = context.pending_action
        raw = cast(Mapping[str, object], state.get("confirmation_payload") or {})
        decision = raw.get("decision")
        if isinstance(decision, Mapping):
            decision = decision.get("decision") or decision.get("kind")
        if pending is None or decision not in {"approve", "reject"}:
            return {"failure_stage": "execution_failure"}
        ids = _ids(config)
        resolved = deps.turn.resolve_pending(
            act_id=f"resolve:{pending.act_id}:{pending.ordinal}",
            context=context,
            pending_ref=pending.pending_ref,
            decision=cast(str, decision),
            correlation_id=ids["correlation_id"],
            idempotency_key=(
                f"conversation:{ids['session_id']}:{state['message_id']}:"
                f"resolve:{pending.ordinal}"
            ),
        )
        executed = list(state.get("executed") or [])
        outcomes = list(state.get("outcomes") or [])
        executed.append(_executed_to_dict(resolved))
        outcomes.append(_outcome_to_dict(_outcome_from_executed(resolved)))
        return {"executed": executed, "outcomes": outcomes}

    def _compose_reply(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        result = _result_from_state(state)
        reply = deps.reply.compose(result)
        return {"reply": asdict(reply)}

    def _persist_turn(
        state: ConversationGraphState, config: RunnableConfig
    ) -> dict[str, object]:
        return {}

    def _route_after_execute(state: ConversationGraphState) -> str:
        return "compose_reply"

    def _route_after_reload(state: ConversationGraphState) -> str:
        return "compose_reply"

    def _route_after_reply(state: ConversationGraphState) -> str:
        context = _context_from_dict(state.get("context") or {})
        if _turn_requires_confirmation(state, context):
            return "require_confirmation"
        return "persist_turn"

    builder = StateGraph(ConversationGraphState)
    builder.add_node("load_context", _load_context)
    builder.add_node("interpret_turn", _interpret_turn)
    builder.add_node("plan_segment", _plan_segment)
    builder.add_node("execute_segment", _execute_segment)
    builder.add_node("reload_context", _reload_context)
    builder.add_node("require_confirmation", _require_confirmation)
    builder.add_node("resolve_pending", _resolve_pending)
    builder.add_node("compose_reply", _compose_reply)
    builder.add_node("persist_turn", _persist_turn)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "interpret_turn")
    builder.add_edge("interpret_turn", "plan_segment")
    builder.add_edge("plan_segment", "execute_segment")
    builder.add_conditional_edges(
        "execute_segment",
        _route_after_execute,
        {
            "compose_reply": "compose_reply",
        },
    )
    builder.add_conditional_edges(
        "reload_context",
        _route_after_reload,
        {"compose_reply": "compose_reply"},
    )
    builder.add_edge("require_confirmation", "resolve_pending")
    builder.add_edge("resolve_pending", "reload_context")
    builder.add_conditional_edges(
        "compose_reply",
        _route_after_reply,
        {
            "require_confirmation": "require_confirmation",
            "persist_turn": "persist_turn",
        },
    )
    builder.add_edge("persist_turn", END)
    compiled = builder.compile(checkpointer=cast(Any, checkpointer))
    return AgentGraph(compiled=compiled, deps=deps)


def _context_to_dict(context: TurnContext) -> dict[str, object]:
    return asdict(context)


def _turn_requires_confirmation(
    state: ConversationGraphState,
    context: TurnContext,
) -> bool:
    """Require confirmation only for a pending effect of this graph turn."""
    pending = context.pending_action
    if pending is None:
        return False
    if any(item.get("status") == "pending" for item in state.get("outcomes") or []):
        return True
    return any(
        item.get("effect_key") == "pending.resolved"
        for item in state.get("executed") or []
    )


def _context_from_dict(data: Mapping[str, object]) -> TurnContext:
    return TurnContext(
        user_id=str(data["user_id"]),
        session_id=str(data["session_id"]),
        active_radar_ref=_optional_str(data.get("active_radar_ref")),
        active_radar_version=_optional_int(data.get("active_radar_version")),
        current_filters=tuple(
            HardFilter(
                filter_key=str(item["filter_key"]),
                value=(
                    tuple(value) if isinstance(value, list) else value
                ),
                force="hard",
            )
            for item in _list(data.get("current_filters"))
            if (value := item.get("value")) is not None
        ),
        active_desires=tuple(
            _desire_from_dict(item)
            for item in _list(data.get("active_desires"))
        ),
        pending_action=(
            PendingAction(
                pending_ref=str(data["pending_action"]["pending_ref"]),
                act_id=str(data["pending_action"].get("act_id", "")),
                ordinal=int(data["pending_action"].get("ordinal", 1)),
                total=int(data["pending_action"].get("total", 1)),
            )
            if data.get("pending_action") is not None
            else None
        ),
        focused_entity=(
            FocusedEntity(entity_ref=str(data["focused_entity"]["entity_ref"]))
            if data.get("focused_entity") is not None
            else None
        ),
        verified_listing_refs=tuple(_strings(data.get("verified_listing_refs"))),
        allowed_capabilities=tuple(_strings(data.get("allowed_capabilities"))),
        untrusted_content=tuple(
            UntrustedContent(
                source=str(item["source"]),
                text=str(item["text"]),
                may_supply_evidence=False,
            )
            for item in _list(data.get("untrusted_content"))
        ),
        context_schema_version="5",
        correlation_id=str(data["correlation_id"]),
    )


def _desire_from_dict(data: Mapping[str, object]) -> DesireView:
    return DesireView(
        desire_ref=str(data["desire_ref"]),
        raw_text=str(data["raw_text"]),
        subject_ref=str(data["subject_ref"]),
        concept_links=tuple(
            ConceptLink(
                concept_ref=str(item["concept_ref"]),
                confidence=float(item["confidence"]),
                polarity=cast(Literal["positive", "negative"], item["polarity"]),
                intensity=cast(
                    Literal["low", "medium", "high", "essential"],
                    item["intensity"],
                ),
                evidence_spans=_spans(item.get("evidence_spans")),
                force="soft",
            )
            for item in _list(data.get("concept_links"))
        ),
    )


def _spans(value: object) -> tuple[EvidenceSpan, ...]:
    return tuple(
        EvidenceSpan(
            start=int(item["start"]),
            end=int(item["end"]),
            text=str(item["text"]),
        )
        for item in _list(value)
    )


def _interpretation_to_dict(
    interpretation: TurnInterpretation,
) -> dict[str, object]:
    return asdict(interpretation)


def _interpretation_from_dict(
    data: Mapping[str, object],
) -> TurnInterpretation:
    return TurnInterpretation(
        model_version=str(data.get("model_version", "")),
        prompt_version=str(data.get("prompt_version", "")),
        acts=tuple(_act_from_dict(item) for item in _list(data.get("acts"))),
    )


def _act_from_dict(data: Mapping[str, object]) -> ConversationAct:
    kind = str(data.get("kind", ""))
    common = {
        "act_id": str(data["act_id"]),
        "confidence": float(data["confidence"]),
        "evidence_spans": _spans(data.get("evidence_spans")),
    }
    if kind == "create_radar":
        return CreateRadar(**common, name=_optional_str(data.get("name")))
    if kind == "set_filter":
        return SetFilter(
            **common,
            filter_key=str(data["filter_key"]),
            value=data["value"],
        )
    if kind == "clear_filter":
        return ClearFilter(**common, filter_key=str(data["filter_key"]))
    if kind == "express_desire":
        return ExpressDesire(
            **common,
            raw_text=str(data["raw_text"]),
            subject_ref=str(data["subject_ref"]),
            concept_links=_links(data.get("concept_links")),
        )
    if kind == "revise_desire":
        return ReviseDesire(
            **common,
            desire_ref=_optional_str(data.get("desire_ref")),
            raw_text=str(data["raw_text"]),
            concept_links=_links(data.get("concept_links")),
        )
    if kind == "withdraw_desire":
        return WithdrawDesire(
            **common, desire_ref=_optional_str(data.get("desire_ref"))
        )
    if kind == "record_feedback":
        return RecordFeedback(
            **common,
            listing_ref=str(data["listing_ref"]),
            feedback_type=str(data["feedback_type"]),
            raw_text=_optional_str(data.get("raw_text")),
        )
    if kind == "resolve_pending":
        return ResolvePending(
            **common,
            pending_ref=str(data["pending_ref"]),
            decision=str(data["decision"]),
        )
    if kind == "query":
        return Query(**common, query_text=str(data["query_text"]))
    if kind == "unsupported_request":
        return UnsupportedRequest(
            **common, request_text=str(data["request_text"])
        )
    raise ValueError(f"unknown act kind: {kind}")


def _links(value: object) -> tuple[ConceptLink, ...]:
    return tuple(
        ConceptLink(
            concept_ref=str(item["concept_ref"]),
            confidence=float(item["confidence"]),
            polarity=cast(Literal["positive", "negative"], item["polarity"]),
            intensity=cast(
                Literal["low", "medium", "high", "essential"], item["intensity"]
            ),
            evidence_spans=_spans(item.get("evidence_spans")),
            force="soft",
        )
        for item in _list(value)
    )


def _plan_to_dict(plan: TurnPlan) -> dict[str, object]:
    return {
        "decisions": [asdict(item) for item in plan.decisions],
        "commands": [
            {**asdict(item), "command_kind": type(item).__name__}
            for item in plan.commands
        ],
    }


def _plan_from_dict(data: Mapping[str, object]) -> TurnPlan:
    return TurnPlan(
        decisions=tuple(
            ActDecision(
                act_id=str(item["act_id"]),
                status=str(item["status"]),
                reason_code=_optional_str(item.get("reason_code")),
            )
            for item in _list(data.get("decisions"))
        ),
        commands=tuple(
            _command_from_dict(item)
            for item in _list(data.get("commands"))
        ),
    )


def _command_from_dict(data: Mapping[str, object]) -> Command:
    name = str(data.get("command_kind") or "unknown")
    if name == "CreateRadarCommand":
        return CreateRadarCommand(
            act_id=str(data["act_id"]), name=_optional_str(data.get("name"))
        )
    if name == "SetFilterCommand":
        return SetFilterCommand(
            act_id=str(data["act_id"]),
            filter_key=str(data["filter_key"]),
            value=data["value"],
            expected_profile_version=_optional_int(data.get("expected_profile_version")),
        )
    if name == "ClearFilterCommand":
        return ClearFilterCommand(
            act_id=str(data["act_id"]),
            filter_key=str(data["filter_key"]),
            expected_profile_version=_optional_int(data.get("expected_profile_version")),
        )
    if name == "RecordDesireCommand":
        return RecordDesireCommand(
            act_id=str(data["act_id"]),
            raw_text=str(data["raw_text"]),
            subject_ref=str(data["subject_ref"]),
            concept_links=_links(data.get("concept_links")),
        )
    if name == "ReviseDesireCommand":
        return ReviseDesireCommand(
            act_id=str(data["act_id"]),
            desire_ref=str(data["desire_ref"]),
            raw_text=str(data["raw_text"]),
            concept_links=_links(data.get("concept_links")),
        )
    if name == "WithdrawDesireCommand":
        return WithdrawDesireCommand(
            act_id=str(data["act_id"]), desire_ref=str(data["desire_ref"])
        )
    if name == "RecordFeedbackCommand":
        return RecordFeedbackCommand(
            act_id=str(data["act_id"]),
            listing_id=UUID(str(data["listing_id"])),
            feedback_type=str(data["feedback_type"]),
            raw_text=_optional_str(data.get("raw_text")),
        )
    raise ValueError(f"unknown command: {name}")


def _executed_to_dict(item: ExecutedAct) -> dict[str, object]:
    return asdict(item)


def _outcome_to_dict(item: ActOutcome) -> dict[str, object]:
    return asdict(item)


def _outcome_from_executed(item: ExecutedAct) -> ActOutcome:
    return ActOutcome(
        act_id=item.act_id,
        status=item.status,
        reason_code=item.reason_code,
        object_ref=item.object_ref,
    )


def _result_from_state(state: ConversationGraphState) -> ConversationTurnResult:
    return ConversationTurnResult(
        context=_context_from_dict(state.get("context") or {}),
        interpretation=_interpretation_from_dict(state.get("interpretation") or {})
        if state.get("interpretation") is not None
        else None,
        plan=_plan_from_dict(state.get("plan") or {})
        if state.get("plan") is not None
        else None,
        executed=tuple(
            ExecutedAct(
                act_id=str(item["act_id"]),
                effect_key=str(item["effect_key"]),
                status=str(item["status"]),
                object_ref=_optional_str(item.get("object_ref")),
                reason_code=_optional_str(item.get("reason_code")),
            )
            for item in state.get("executed") or []
        ),
        outcomes=tuple(
            ActOutcome(
                act_id=str(item["act_id"]),
                status=str(item["status"]),
                reason_code=_optional_str(item.get("reason_code")),
                object_ref=_optional_str(item.get("object_ref")),
            )
            for item in state.get("outcomes") or []
        ),
        failure_stage=str(state["failure_stage"])
        if state.get("failure_stage") is not None
        else None,
    )


def _list(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strings(value: object) -> list[str]:
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _is_provider_error(error: Exception) -> bool:
    from umbral.agent.intent import InterpretationContractFailed

    return isinstance(error, InterpretationContractFailed) and (
        error.reason == "provider_failure" or error.reason.startswith("provider")
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
