"""Separate V5 conversation graph topology (load/plan/execute/reply/persist).

The graph is a thin routing shell over the V5 turn module: its nodes call the
turn service phases and the reply composer; no policy, execution, or ranking
logic lives inside graph nodes. State is JSON-serializable under
``state-schema-v5.json``.
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

from umbral.application.conversation.v5.contracts import (
    ActDecisionV5,
    ActOutcomeV5,
    ClearFilter,
    ClearFilterCommand,
    CommandV5,
    ConceptLinkV5,
    ConversationActV5,
    ConversationTurnResultV5,
    CreateRadar,
    CreateRadarCommand,
    DesireViewV5,
    EvidenceSpan,
    ExecutedActV5,
    ExpressDesire,
    FocusedEntityV5,
    HardFilterV5,
    PendingActionV5,
    Query,
    RecordDesireCommand,
    RecordFeedback,
    RecordFeedbackCommand,
    ResolvePending,
    ReviseDesire,
    ReviseDesireCommand,
    SetFilter,
    SetFilterCommand,
    TurnContextV5,
    TurnInterpretationV5,
    TurnPlanV5,
    UnsupportedRequest,
    UntrustedContentV5,
    WithdrawDesire,
    WithdrawDesireCommand,
)
from umbral.application.conversation.v5.reply import ReplyV5


class ConversationGraphStateV5(TypedDict, total=False):
    """Serializable graph state matching ``state-schema-v5.json``."""

    contract_version: Literal["5"]
    schema_version: Literal["conversation-state-v5"]
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


class TurnServiceLikeV5(Protocol):
    def load_context(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> TurnContextV5: ...

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContextV5,
        correlation_id: UUID,
    ) -> TurnInterpretationV5: ...

    def plan(
        self,
        *,
        user_message: str,
        context: TurnContextV5,
        interpretation: TurnInterpretationV5,
    ) -> TurnPlanV5: ...

    def execute(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        message_id: UUID,
        message_text: str,
        correlation_id: UUID,
        context: TurnContextV5,
        interpretation: TurnInterpretationV5,
        plan: TurnPlanV5,
    ) -> ConversationTurnResultV5: ...


class ReplyComposerV5Like(Protocol):
    def compose(self, result: ConversationTurnResultV5) -> ReplyV5: ...


@dataclass(frozen=True, slots=True)
class GraphDepsV5:
    turn: TurnServiceLikeV5
    reply: ReplyComposerV5Like


def build_graph_v5(
    *,
    dependencies: GraphDepsV5,
    checkpointer: object | None = None,
) -> object:
    """Build the compiled V5 graph matching ``graph-topology-v5.json``."""
    deps = dependencies

    def _ids(config: Mapping[str, object]) -> dict[str, UUID]:
        configurable = cast(Mapping[str, object], config.get("configurable") or {})
        return {
            "user_id": UUID(str(configurable["user_id"])),
            "session_id": UUID(str(configurable["session_id"])),
            "correlation_id": UUID(str(configurable["correlation_id"])),
        }

    def _load_context(
        state: ConversationGraphStateV5, config: RunnableConfig
    ) -> dict[str, object]:
        ids = _ids(config)
        context = deps.turn.load_context(
            user_id=ids["user_id"],
            session_id=ids["session_id"],
            correlation_id=ids["correlation_id"],
        )
        return {"context": _context_to_dict(context)}

    def _interpret_turn(
        state: ConversationGraphStateV5, config: RunnableConfig
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
        state: ConversationGraphStateV5, config: RunnableConfig
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
        state: ConversationGraphStateV5, config: RunnableConfig
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
        return {
            "context": _context_to_dict(result.context),
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
        state: ConversationGraphStateV5, config: RunnableConfig
    ) -> dict[str, object]:
        ids = _ids(config)
        context = deps.turn.load_context(
            user_id=ids["user_id"],
            session_id=ids["session_id"],
            correlation_id=ids["correlation_id"],
        )
        return {"context": _context_to_dict(context)}

    def _require_confirmation(
        state: ConversationGraphStateV5, config: RunnableConfig
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": "conversation_confirmation",
            "outcomes": [
                dict(item)
                for item in (state.get("outcomes") or [])
                if item.get("status") == "pending"
            ],
        }
        decision = interrupt(payload)
        return {"confirmation_payload": {"decision": decision}}

    def _compose_reply(
        state: ConversationGraphStateV5, config: RunnableConfig
    ) -> dict[str, object]:
        result = _result_from_state(state)
        reply = deps.reply.compose(result)
        return {"reply": asdict(reply)}

    def _persist_turn(
        state: ConversationGraphStateV5, config: RunnableConfig
    ) -> dict[str, object]:
        return {}

    def _route_after_execute(state: ConversationGraphStateV5) -> str:
        if state.get("failure_stage") is not None:
            return "compose_reply"
        outcomes = state.get("outcomes") or []
        if any(item.get("status") == "pending" for item in outcomes):
            return "require_confirmation"
        return "compose_reply"

    builder = StateGraph(ConversationGraphStateV5)
    builder.add_node("load_context", _load_context)
    builder.add_node("interpret_turn", _interpret_turn)
    builder.add_node("plan_segment", _plan_segment)
    builder.add_node("execute_segment", _execute_segment)
    builder.add_node("reload_context", _reload_context)
    builder.add_node("require_confirmation", _require_confirmation)
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
            "reload_context": "reload_context",
            "require_confirmation": "require_confirmation",
            "compose_reply": "compose_reply",
        },
    )
    builder.add_edge("reload_context", "plan_segment")
    builder.add_edge("require_confirmation", "reload_context")
    builder.add_edge("compose_reply", "persist_turn")
    builder.add_edge("persist_turn", END)
    compiled = builder.compile(checkpointer=cast(Any, checkpointer))
    return compiled


def _context_to_dict(context: TurnContextV5) -> dict[str, object]:
    return asdict(context)


def _context_from_dict(data: Mapping[str, object]) -> TurnContextV5:
    return TurnContextV5(
        user_id=str(data["user_id"]),
        session_id=str(data["session_id"]),
        active_radar_ref=_optional_str(data.get("active_radar_ref")),
        active_radar_version=_optional_int(data.get("active_radar_version")),
        current_filters=tuple(
            HardFilterV5(
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
            PendingActionV5(pending_ref=str(data["pending_action"]["pending_ref"]))
            if data.get("pending_action") is not None
            else None
        ),
        focused_entity=(
            FocusedEntityV5(entity_ref=str(data["focused_entity"]["entity_ref"]))
            if data.get("focused_entity") is not None
            else None
        ),
        verified_listing_refs=tuple(_strings(data.get("verified_listing_refs"))),
        allowed_capabilities=tuple(_strings(data.get("allowed_capabilities"))),
        untrusted_content=tuple(
            UntrustedContentV5(
                source=str(item["source"]),
                text=str(item["text"]),
                may_supply_evidence=False,
            )
            for item in _list(data.get("untrusted_content"))
        ),
        context_schema_version="5",
        correlation_id=str(data["correlation_id"]),
    )


def _desire_from_dict(data: Mapping[str, object]) -> DesireViewV5:
    return DesireViewV5(
        desire_ref=str(data["desire_ref"]),
        raw_text=str(data["raw_text"]),
        subject_ref=str(data["subject_ref"]),
        concept_links=tuple(
            ConceptLinkV5(
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
    interpretation: TurnInterpretationV5,
) -> dict[str, object]:
    return asdict(interpretation)


def _interpretation_from_dict(
    data: Mapping[str, object],
) -> TurnInterpretationV5:
    return TurnInterpretationV5(
        model_version=str(data.get("model_version", "")),
        prompt_version=str(data.get("prompt_version", "")),
        acts=tuple(_act_from_dict(item) for item in _list(data.get("acts"))),
    )


def _act_from_dict(data: Mapping[str, object]) -> ConversationActV5:
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


def _links(value: object) -> tuple[ConceptLinkV5, ...]:
    return tuple(
        ConceptLinkV5(
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


def _plan_to_dict(plan: TurnPlanV5) -> dict[str, object]:
    return {
        "decisions": [asdict(item) for item in plan.decisions],
        "commands": [
            {**asdict(item), "command_kind": type(item).__name__}
            for item in plan.commands
        ],
    }


def _plan_from_dict(data: Mapping[str, object]) -> TurnPlanV5:
    return TurnPlanV5(
        decisions=tuple(
            ActDecisionV5(
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


def _command_from_dict(data: Mapping[str, object]) -> CommandV5:
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


def _executed_to_dict(item: ExecutedActV5) -> dict[str, object]:
    return asdict(item)


def _outcome_to_dict(item: ActOutcomeV5) -> dict[str, object]:
    return asdict(item)


def _result_from_state(state: ConversationGraphStateV5) -> ConversationTurnResultV5:
    return ConversationTurnResultV5(
        context=_context_from_dict(state.get("context") or {}),
        interpretation=_interpretation_from_dict(state.get("interpretation") or {})
        if state.get("interpretation") is not None
        else None,
        plan=_plan_from_dict(state.get("plan") or {})
        if state.get("plan") is not None
        else None,
        executed=tuple(
            ExecutedActV5(
                act_id=str(item["act_id"]),
                effect_key=str(item["effect_key"]),
                status=str(item["status"]),
                object_ref=_optional_str(item.get("object_ref")),
                reason_code=_optional_str(item.get("reason_code")),
            )
            for item in state.get("executed") or []
        ),
        outcomes=tuple(
            ActOutcomeV5(
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
    from umbral.agent.intent.v5 import InterpretationContractFailed

    return isinstance(error, InterpretationContractFailed) and (
        error.reason == "provider_failure" or error.reason.startswith("provider")
    )


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
