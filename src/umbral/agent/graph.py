"""Topology v1/v2 graph for the conversational runtime (UM-H4-002, FR-016).

The graph is provider-agnostic: model gateway, conversation sink, run
recorder, checkpointer and (v2) the tool executor arrive via the constructor
(the agent layer never imports infrastructure, R-03). Effects are deduplicated
through the ``context.effects_applied`` ledger so a resume never repeats them
(FR-014).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from umbral.agent.events import ReplyFragment, RuntimeEvent, ToolActivity
from umbral.agent.intent.clarification import (
    ClarificationPlan,
    render_question,
)
from umbral.agent.intent.clarification import (
    decide as decide_clarification,
)
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.intent.policy import validate_tool_calls
from umbral.agent.state import (
    STATE_SCHEMA_VERSION,
    AgentState,
    build_initial_state,
)
from umbral.agent.tools.executor import ToolExecutor
from umbral.application.agent.contracts import ModelCall, ModelResult, NodeRun
from umbral.application.agent.ports import ModelGateway, RunRecorder
from umbral.application.agent.tools.contracts import Proposal
from umbral.application.agent.tools.ports import (
    PreferenceDecisionGateway,
    ProposalDecisionGateway,
)
from umbral.application.chat.ports import ConversationGateway

TOPOLOGY_VERSION = 1
TOOLS_TOPOLOGY_VERSION = 2
CHAT_TOPOLOGY_VERSION = 3

_EFFECT_USER_MESSAGE = "user_message"
_EFFECT_ASSISTANT_MESSAGE = "assistant_message"

_PROPOSE_TOOL = "propose_search_profile_update"
_PREFERENCE_PROPOSE_TOOL = "propose_search_preference_update"
_PREFERENCE_REMOVAL_TOOL = "propose_search_preference_removal"
_LEARNING_CONFIRM_TOOL = "propose_learning_confirmation"
_PROPOSE_TOOLS = frozenset(
    {
        _PROPOSE_TOOL,
        _PREFERENCE_PROPOSE_TOOL,
        _PREFERENCE_REMOVAL_TOOL,
        _LEARNING_CONFIRM_TOOL,
    }
)
_PREFERENCE_TOOLS = frozenset(
    {_PREFERENCE_PROPOSE_TOOL, _PREFERENCE_REMOVAL_TOOL, _LEARNING_CONFIRM_TOOL}
)


@dataclass(slots=True)
class GraphSinks:
    """Per-run event emitter; the runtime swaps ``emit`` before each run."""

    emit: Callable[[RuntimeEvent], None] = field(default=lambda _event: None)


@dataclass(slots=True)
class GraphDeps:
    gateway: ModelGateway
    conversation: ConversationGateway
    recorder: RunRecorder
    sinks: GraphSinks
    clock: Callable[[], datetime]
    model_version: str
    prompt_version: str
    schema_version: str
    reply_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AgentGraph:
    """The compiled topology v1 graph plus its per-run dependency holder."""

    compiled: Any
    deps: GraphDeps


@dataclass(slots=True)
class GraphDepsV2(GraphDeps):
    """Topology v2 dependencies: v1 plus the tool executor and loop bound."""

    tool_executor: ToolExecutor
    max_calls_per_turn: int


@dataclass(frozen=True, slots=True)
class AgentGraphV2:
    """The compiled topology v2 graph plus its per-run dependency holder."""

    compiled: Any
    deps: GraphDepsV2


@dataclass(slots=True)
class GraphDepsV3(GraphDepsV2):
    """Topology v3 dependencies: intent compiler, decision seam and policies."""

    intent_compiler: IntentCompiler
    decision_gateway: ProposalDecisionGateway
    preference_gateway: PreferenceDecisionGateway
    high_impact_keys: tuple[str, ...]
    clarification_min_confidence: float
    clarification_max_rounds: int
    reply_chunk_words: int
    reply_max_refs: int


@dataclass(frozen=True, slots=True)
class AgentGraphV3:
    """The compiled topology v3 graph plus its per-run dependency holder."""

    compiled: Any
    deps: GraphDepsV3


def build_topology_v1(
    *,
    gateway: ModelGateway,
    conversation: ConversationGateway,
    recorder: RunRecorder,
    saver: Any,
    clock: Callable[[], datetime],
    model_version: str,
    prompt_version: str,
    schema_version: str,
    reply_schema: Mapping[str, object],
) -> AgentGraph:
    deps = GraphDeps(
        gateway=gateway,
        conversation=conversation,
        recorder=recorder,
        sinks=GraphSinks(),
        clock=clock,
        model_version=model_version,
        prompt_version=prompt_version,
        schema_version=schema_version,
        reply_schema=reply_schema,
    )

    def _start(state: AgentState) -> dict[str, object]:
        context = _context(state)
        node_started = deps.clock()
        effects = dict(_effects(context))
        if _EFFECT_USER_MESSAGE not in effects:
            conversation.append_user_message(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                text=str(context.get("user_message_text", "")),
                correlation_id=_uuid(context, "correlation_id"),
                now=deps.clock(),
            )
            effects[_EFFECT_USER_MESSAGE] = _str(context, "run_id")
        context["effects_applied"] = effects
        _finish_node(
            recorder=recorder,
            node_name="start",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context}

    def _generate_reply(state: AgentState) -> dict[str, object]:
        context = _context(state)
        run_id = _uuid(context, "run_id")
        node_started = deps.clock()
        errors = list(state.get("errors") or [])
        try:
            result = deps.gateway.generate_structured(
                messages=(_user_message(context),),
                schema=deps.reply_schema,
                schema_version=deps.schema_version,
                prompt_version=deps.prompt_version,
                model_version=deps.model_version,
            )
        except Exception as exc:  # noqa: BLE001 - unknown provider failure
            _finish_node(
                recorder=recorder,
                node_name="generate_reply",
                graph_run_id=run_id,
                correlation_id=_uuid(context, "correlation_id"),
                started_at=node_started,
                finished_at=deps.clock(),
                status="interrupted",
                error_summary={
                    "code": "agent.provider_exception",
                    "kind": type(exc).__name__,
                },
            )
            raise

        deps.recorder.record_model_call(
            ModelCall(
                call_id=uuid4(),
                graph_run_id=run_id,
                model_version=result.model_version,
                prompt_version=deps.prompt_version,
                schema_version=deps.schema_version,
                status=result.status,
                correlation_id=_uuid(context, "correlation_id"),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                error_code=result.error_code,
            )
        )
        raw_usage = context.get("token_usage")
        usage: Mapping[str, object] = (
            raw_usage if isinstance(raw_usage, Mapping) else {}
        )
        if result.status == "success" and result.content is not None:
            text = str(result.content.get("reply_text", ""))
            refs = result.content.get("refs")
            ref_list = [dict(item) for item in refs] if isinstance(refs, list) else []
            deps.sinks.emit(ReplyFragment(run_id=run_id, delta=text))
            context["generated_reply"] = {"text": text, "refs": ref_list}
            context["token_usage"] = _accumulate_usage(usage, result)
        else:
            errors.append({"code": result.error_code or "agent.generation_failed"})
        _finish_node(
            recorder=recorder,
            node_name="generate_reply",
            graph_run_id=run_id,
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="failed" if errors else "completed",
            error_summary=errors[-1] if errors else None,
        )
        return {"context": context, "errors": errors}

    def _persist_reply(state: AgentState) -> dict[str, object]:
        context = _context(state)
        effects = dict(_effects(context))
        if _EFFECT_ASSISTANT_MESSAGE in effects:
            return {"context": context}
        reply = context.get("generated_reply")
        if not isinstance(reply, Mapping):
            return {"context": context}
        node_started = deps.clock()
        message = deps.conversation.persist_assistant_message(
            user_id=_uuid(context, "user_id"),
            session_id=_uuid(context, "session_id"),
            text=str(reply.get("text", "")),
            refs=tuple(
                {"entity": str(item["entity"]), "id": str(item["id"])}
                for item in reply.get("refs", [])
                if isinstance(item, Mapping)
            ),
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            now=deps.clock(),
        )
        effects[_EFFECT_ASSISTANT_MESSAGE] = _str(context, "run_id")
        context["effects_applied"] = effects
        context["assistant_message_id"] = str(message.message_id)
        _finish_node(
            recorder=recorder,
            node_name="persist_reply",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context}

    builder = StateGraph(AgentState)
    builder.add_node("start", _start)
    builder.add_node("generate_reply", _generate_reply)
    builder.add_node("persist_reply", _persist_reply)
    builder.add_edge(START, "start")
    builder.add_edge("start", "generate_reply")
    builder.add_edge("generate_reply", "persist_reply")
    builder.add_edge("persist_reply", END)
    compiled = builder.compile(checkpointer=saver)
    return AgentGraph(compiled=compiled, deps=deps)


def build_topology_v2(
    *,
    gateway: ModelGateway,
    conversation: ConversationGateway,
    recorder: RunRecorder,
    saver: Any,
    tool_executor: ToolExecutor,
    clock: Callable[[], datetime],
    model_version: str,
    prompt_version: str,
    schema_version: str,
    reply_schema: Mapping[str, object],
    max_calls_per_turn: int,
) -> AgentGraphV2:
    """Build the topology v2 graph with the bounded tool loop (R-14).

    ``generate_reply`` may emit ``tool_calls``; the ``run_tools`` node
    executes them through the executor (recording one tool run per call),
    accumulates redacted results and loops back to ``generate_reply`` so the
    final reply can be grounded. The loop is bounded by ``max_calls_per_turn``.
    """

    deps = GraphDepsV2(
        gateway=gateway,
        conversation=conversation,
        recorder=recorder,
        sinks=GraphSinks(),
        clock=clock,
        model_version=model_version,
        prompt_version=prompt_version,
        schema_version=schema_version,
        reply_schema=reply_schema,
        tool_executor=tool_executor,
        max_calls_per_turn=max_calls_per_turn,
    )

    def _start(state: AgentState) -> dict[str, object]:
        context = _context(state)
        node_started = deps.clock()
        effects = dict(_effects(context))
        if _EFFECT_USER_MESSAGE not in effects:
            conversation.append_user_message(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                text=str(context.get("user_message_text", "")),
                correlation_id=_uuid(context, "correlation_id"),
                now=deps.clock(),
            )
            effects[_EFFECT_USER_MESSAGE] = _str(context, "run_id")
        context["effects_applied"] = effects
        _finish_node(
            recorder=recorder,
            node_name="start",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context}

    def _generate_reply(state: AgentState) -> dict[str, object]:
        context = _context(state)
        run_id = _uuid(context, "run_id")
        node_started = deps.clock()
        errors = list(state.get("errors") or [])
        messages = [_user_message(context)]
        results_context = context.get("tool_results_context")
        if results_context:
            messages.append({"role": "tool", "content": results_context})
        try:
            result = deps.gateway.generate_structured(
                messages=tuple(messages),
                schema=deps.reply_schema,
                schema_version=deps.schema_version,
                prompt_version=deps.prompt_version,
                model_version=deps.model_version,
            )
        except Exception as exc:  # noqa: BLE001 - unknown provider failure
            _finish_node(
                recorder=recorder,
                node_name="generate_reply",
                graph_run_id=run_id,
                correlation_id=_uuid(context, "correlation_id"),
                started_at=node_started,
                finished_at=deps.clock(),
                status="interrupted",
                error_summary={
                    "code": "agent.provider_exception",
                    "kind": type(exc).__name__,
                },
            )
            raise

        deps.recorder.record_model_call(
            ModelCall(
                call_id=uuid4(),
                graph_run_id=run_id,
                model_version=result.model_version,
                prompt_version=deps.prompt_version,
                schema_version=deps.schema_version,
                status=result.status,
                correlation_id=_uuid(context, "correlation_id"),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                error_code=result.error_code,
            )
        )
        raw_usage = context.get("token_usage")
        usage: Mapping[str, object] = (
            raw_usage if isinstance(raw_usage, Mapping) else {}
        )
        tool_calls: list[dict[str, object]] = []
        if result.status == "success" and result.content is not None:
            text = str(result.content.get("reply_text", ""))
            refs = result.content.get("refs")
            ref_list = [dict(item) for item in refs] if isinstance(refs, list) else []
            calls = result.content.get("tool_calls")
            if isinstance(calls, list):
                tool_calls = [
                    dict(item) for item in calls if isinstance(item, Mapping)
                ]
            deps.sinks.emit(ReplyFragment(run_id=run_id, delta=text))
            context["generated_reply"] = {"text": text, "refs": ref_list}
            context["token_usage"] = _accumulate_usage(usage, result)
        else:
            errors.append({"code": result.error_code or "agent.generation_failed"})
        _finish_node(
            recorder=recorder,
            node_name="generate_reply",
            graph_run_id=run_id,
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="failed" if errors else "completed",
            error_summary=errors[-1] if errors else None,
        )
        return {"context": context, "errors": errors, "tool_calls": tool_calls}

    def _route_from_generate(state: AgentState) -> str:
        calls = state.get("tool_calls") or []
        if not calls:
            return "persist_reply"
        count = _as_int(_context(state).get("tool_loop_count"), 0)
        if count >= max_calls_per_turn:
            return "persist_reply"
        return "run_tools"

    def _run_tools(state: AgentState) -> dict[str, object]:
        context = _context(state)
        calls = state.get("tool_calls") or []
        count = _as_int(context.get("tool_loop_count"), 0)
        budget = max_calls_per_turn - count
        if budget <= 0 or not calls:
            context["tool_loop_exhausted"] = True
            return {"context": context, "tool_calls": []}
        runnable = calls[:budget]
        results: list[dict[str, object]] = []
        for call in runnable:
            name = str(call.get("tool", ""))
            raw_args = call.get("args")
            args = dict(raw_args) if isinstance(raw_args, Mapping) else {}
            outcome = deps.tool_executor.execute(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                run_id=_uuid(context, "run_id"),
                correlation_id=_uuid(context, "correlation_id"),
                name=name,
                args=args,
            )
            results.append(
                {
                    "tool": name,
                    "status": outcome.status,
                    "result": dict(outcome.result) if outcome.result else None,
                    "error_code": outcome.error_code,
                }
            )
        context["tool_loop_count"] = count + len(runnable)
        context["tool_results_context"] = results
        existing = list(state.get("tool_results") or [])
        return {
            "context": context,
            "tool_calls": [],
            "tool_results": existing + results,
        }

    def _route_from_tools(state: AgentState) -> str:
        if _context(state).get("tool_loop_exhausted"):
            return "persist_reply"
        return "generate_reply"

    def _persist_reply(state: AgentState) -> dict[str, object]:
        context = _context(state)
        effects = dict(_effects(context))
        if _EFFECT_ASSISTANT_MESSAGE in effects:
            return {"context": context}
        reply = context.get("generated_reply")
        if not isinstance(reply, Mapping):
            return {"context": context}
        node_started = deps.clock()
        message = deps.conversation.persist_assistant_message(
            user_id=_uuid(context, "user_id"),
            session_id=_uuid(context, "session_id"),
            text=str(reply.get("text", "")),
            refs=tuple(
                {"entity": str(item["entity"]), "id": str(item["id"])}
                for item in reply.get("refs", [])
                if isinstance(item, Mapping)
            ),
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            now=deps.clock(),
        )
        effects[_EFFECT_ASSISTANT_MESSAGE] = _str(context, "run_id")
        context["effects_applied"] = effects
        context["assistant_message_id"] = str(message.message_id)
        _finish_node(
            recorder=recorder,
            node_name="persist_reply",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context}

    builder = StateGraph(AgentState)
    builder.add_node("start", _start)
    builder.add_node("generate_reply", _generate_reply)
    builder.add_node("run_tools", _run_tools)
    builder.add_node("persist_reply", _persist_reply)
    builder.add_edge(START, "start")
    builder.add_edge("start", "generate_reply")
    builder.add_conditional_edges(
        "generate_reply",
        _route_from_generate,
        {"run_tools": "run_tools", "persist_reply": "persist_reply"},
    )
    builder.add_conditional_edges(
        "run_tools",
        _route_from_tools,
        {"generate_reply": "generate_reply", "persist_reply": "persist_reply"},
    )
    builder.add_edge("persist_reply", END)
    compiled = builder.compile(checkpointer=saver)
    return AgentGraphV2(compiled=compiled, deps=deps)


def build_topology_v3(
    *,
    gateway: ModelGateway,
    conversation: ConversationGateway,
    recorder: RunRecorder,
    saver: Any,
    tool_executor: ToolExecutor,
    intent_compiler: IntentCompiler,
    decision_gateway: ProposalDecisionGateway,
    preference_gateway: PreferenceDecisionGateway,
    clock: Callable[[], datetime],
    model_version: str,
    prompt_version: str,
    schema_version: str,
    reply_schema: Mapping[str, object],
    max_calls_per_turn: int,
    high_impact_keys: tuple[str, ...],
    clarification_min_confidence: float,
    clarification_max_rounds: int,
    reply_chunk_words: int,
    reply_max_refs: int,
) -> AgentGraphV3:
    """Build the topology v3 graph (UM-H4-017..UM-H4-020, R-01..R-05).

    ``compile_intent`` classifies the message and applies the deterministic
    intent-to-tools policy; ``clarify`` renders bounded deterministic
    questions; ``require_confirmation`` interrupts for the HITL proposal
    decision and ``resolve_decision`` resumes with approve/reject/edit.
    """

    deps = GraphDepsV3(
        gateway=gateway,
        conversation=conversation,
        recorder=recorder,
        sinks=GraphSinks(),
        clock=clock,
        model_version=model_version,
        prompt_version=prompt_version,
        schema_version=schema_version,
        reply_schema=reply_schema,
        tool_executor=tool_executor,
        max_calls_per_turn=max_calls_per_turn,
        intent_compiler=intent_compiler,
        decision_gateway=decision_gateway,
        preference_gateway=preference_gateway,
        high_impact_keys=high_impact_keys,
        clarification_min_confidence=clarification_min_confidence,
        clarification_max_rounds=clarification_max_rounds,
        reply_chunk_words=reply_chunk_words,
        reply_max_refs=reply_max_refs,
    )

    def _start(state: AgentState) -> dict[str, object]:
        context = _context(state)
        node_started = deps.clock()
        effects = dict(_effects(context))
        if _EFFECT_USER_MESSAGE not in effects:
            client_message_id = context.get("client_message_id")
            user_message_context = context.get("user_message_context")
            conversation.append_user_message(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                text=str(context.get("user_message_text", "")),
                correlation_id=_uuid(context, "correlation_id"),
                now=deps.clock(),
                client_message_id=(
                    UUID(str(client_message_id)) if client_message_id else None
                ),
                context=(
                    dict(user_message_context)
                    if isinstance(user_message_context, Mapping)
                    else None
                ),
            )
            effects[_EFFECT_USER_MESSAGE] = _str(context, "run_id")
        context["effects_applied"] = effects
        _finish_node(
            recorder=recorder,
            node_name="start",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context}

    def _compile_intent(state: AgentState) -> dict[str, object]:
        context = _context(state)
        node_started = deps.clock()
        errors = list(state.get("errors") or [])
        clarification = state.get("clarification")
        clarification_ctx = (
            clarification if isinstance(clarification, Mapping) else None
        )
        rounds_so_far = _as_int(
            clarification_ctx.get("rounds") if clarification_ctx else None, 0
        )
        try:
            compilation = deps.intent_compiler.compile(
                message_text=str(context.get("user_message_text", "")),
                clarification_context=clarification_ctx,
            )
        except Exception as exc:  # noqa: BLE001 - sanitized below
            code = getattr(exc, "code", "agent.intent_compilation_failed")
            errors.append({"code": str(code)})
            _finish_node(
                recorder=recorder,
                node_name="compile_intent",
                graph_run_id=_uuid(context, "run_id"),
                correlation_id=_uuid(context, "correlation_id"),
                started_at=node_started,
                finished_at=deps.clock(),
                status="failed",
                error_summary={"code": str(code)},
            )
            return {"context": context, "errors": errors}
        intent_data: dict[str, object] = {
            "intent": compilation.intent,
            "parameters": [
                {"key": p.key, "value": p.value, "confidence": p.confidence}
                for p in compilation.parameters
            ],
            "high_impact_missing": list(compilation.high_impact_missing),
            "contradictions": [
                {
                    "key": c.key,
                    "current_value": c.current_value,
                    "requested": c.requested,
                }
                for c in compilation.contradictions
            ],
            "allowed_tools": list(compilation.allowed_tools),
        }
        context["clarification_rounds"] = rounds_so_far
        _finish_node(
            recorder=recorder,
            node_name="compile_intent",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context, "intent": intent_data, "errors": errors}

    def _clarification_plan(state: AgentState) -> ClarificationPlan | None:
        intent_data = state.get("intent")
        if not isinstance(intent_data, Mapping):
            return None
        if intent_data.get("intent") == "fuera_de_alcance":
            return None
        rounds_so_far = _as_int(_context(state).get("clarification_rounds"), 0)
        return decide_clarification(
            intent=str(intent_data.get("intent", "")),
            parameters=[dict(item) for item in intent_data.get("parameters", [])],
            high_impact_missing=[
                str(item) for item in intent_data.get("high_impact_missing", [])
            ],
            contradictions=[
                dict(item) for item in intent_data.get("contradictions", [])
            ],
            high_impact_keys=deps.high_impact_keys,
            min_confidence=deps.clarification_min_confidence,
            rounds=rounds_so_far,
            max_rounds=deps.clarification_max_rounds,
        )

    def _route_from_compile(state: AgentState) -> str:
        if state.get("errors"):
            return "persist_reply"
        if _clarification_plan(state) is not None:
            return "clarify"
        return "generate_reply"

    def _clarify(state: AgentState) -> dict[str, object]:
        context = _context(state)
        plan = _clarification_plan(state)
        if plan is None:
            return {"context": context}
        question = render_question(plan)
        state["clarification"] = {
            "pending_params": list(plan.pending_params),
            "rounds": plan.rounds + 1,
        }
        context["generated_reply"] = {"text": question, "refs": []}
        _finish_node(
            recorder=recorder,
            node_name="clarify",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=deps.clock(),
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context, "clarification": state["clarification"]}

    def _generate_reply(state: AgentState) -> dict[str, object]:
        context = _context(state)
        run_id = _uuid(context, "run_id")
        node_started = deps.clock()
        errors = list(state.get("errors") or [])
        messages: list[Mapping[str, object]] = []
        context_lines: list[str] = []
        user_context = context.get("user_message_context")
        if isinstance(user_context, Mapping):
            entity = str(user_context.get("entity", ""))
            if entity == "listing":
                context_lines.append(
                    f"El usuario esta viendo el listing {user_context.get('id')}."
                )
            elif entity == "comparison":
                listing_ids = user_context.get("listing_ids")
                if isinstance(listing_ids, list) and listing_ids:
                    context_lines.append(
                        "El usuario esta comparando los listings "
                        + ", ".join(str(item) for item in listing_ids)
                        + "."
                    )
                else:
                    context_lines.append(
                        f"El usuario tiene una comparacion abierta "
                        f"({user_context.get('id')})."
                    )
        intent_data = state.get("intent")
        tool_specs: list[dict[str, object]] = []
        if isinstance(intent_data, Mapping):
            allowed = intent_data.get("allowed_tools")
            tool_lines: list[str] = []
            if isinstance(allowed, list):
                for raw_name in allowed:
                    name = str(raw_name)
                    try:
                        spec = deps.tool_executor.registry.get(name)
                    except Exception:  # noqa: BLE001 - unknown tool stays listed by name
                        tool_lines.append(f"- {name}: (contrato no disponible)")
                        continue
                    args = spec.input_schema or {}
                    tool_specs.append(
                        {
                            "name": spec.name,
                            "description": spec.description,
                            "input_schema": dict(args),
                        }
                    )
                    args_text = (
                        ", ".join(
                            f"{key}: {_kind_label(item)}"
                            for key, item in sorted(args.items())
                        )
                        or "ninguno"
                    )
                    tool_lines.append(
                        f"- {name}: {spec.description} (argumentos: {args_text})"
                    )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Intencion compilada: "
                        + str(intent_data.get("intent", ""))
                        + ".\n"
                        + ("\n".join(context_lines) + "\n" if context_lines else "")
                        + "Responde solo sobre este radar usando "
                        "exclusivamente estas tools permitidas:\n"
                        + "\n".join(tool_lines)
                        + "\nUsa las tools cuando la respuesta requiera datos "
                        "del radar; no respondas sobre datos que puedas "
                        "consultar sin haberlos consultado. Si la consulta "
                        "pide oportunidades o matches disponibles, ejecuta "
                        "find_matches antes de responder; si pide la "
                        "explicacion de un listing, ejecuta explain_match; "
                        "si pide datos del listing (precio, ambientes, "
                        "barrio), ejecuta get_listing_detail; "
                        "si pide comparar listings, ejecuta compare_listings. "
                        "Las tools de lectura se ejecutan directamente sin "
                        "pedir permiso; no preguntes si quieres mostrar "
                        "opciones: muestralas. "
                        "El campo refs del JSON debe citar los ids exactos de "
                        "listings o criterios devueltos por las tools; nunca "
                        "inventes ids ni hechos.\n"
                        "Errores de tools: si una tool devuelve error, "
                        "explica brevemente que paso y ofrece una alternativa "
                        "real; nunca inventes datos ni repitas la pregunta. "
                        "Codigos conocidos:\n"
                        "- proposal.unsupported_key: el criterio pedido "
                        "(radio, hard_filters) no existe en el radar; ofrece "
                        "cambiar zona, presupuesto, ambientes o superficie.\n"
                        "- proposal.invalid_change: el cambio no es valido "
                        "(zona fuera de CABA o valor no numerico); propon "
                        "valores validos.\n"
                        "- preference.unknown_concept: esa preferencia "
                        "todavia no la entiendo; ofrece luminosidad, balcon, "
                        "buen estado o tipo de cocina.\n"
                        "- preference.value_required: falta el valor de la "
                        "preferencia (p.ej. cocina integrada o separada); "
                        "pedilo antes de proponer.\n"
                        "- preference.already_pending: ya hay una propuesta "
                        "de preferencia esperando confirmacion para ese "
                        "concepto; pedi que la confirme o la rechace.\n"
                        "- preference.not_active: esa preferencia no esta "
                        "vigente en el radar; ofrece listar las vigentes "
                        "con list_search_preferences.\n"
                        "- tool.no_run: todavia no hay un analisis del radar "
                        "para explicar; ofrece ver los matches disponibles.\n"
                        "- tool.listing_not_accessible: ese listing no esta "
                        "en tu radar; pedi el ID correcto u ofrece los "
                        "matches.\n"
                        "- tool.args_invalid: falta un dato para la accion; "
                        "pedi el dato que falta.\n"
                        "Aprendizaje: cuando record_feedback devuelva "
                        "learning_proposal_id, ofrece aplicar lo aprendido "
                        "con propose_learning_confirmation (nunca lo apliques "
                        "sin confirmacion). Cuando el usuario confirme, la "
                        "preferencia aprendida se registra y el ranking "
                        "recomputa.\n"
                        "Preferencias: cuando propongas una preferencia "
                        "(propose_search_preference_update), ejecuta una sola "
                        "propuesta por turno y usa la frase natural del "
                        "usuario (p.ej. 'luminoso', 'con balcon'). Si el "
                        "impacto devuelto marca contradicts, pregunta al "
                        "usuario como dejar la preferencia antes de "
                        "confirmar. Si el usuario pide quitar una "
                        "preferencia (p.ej. 'saca la de luminosidad'), "
                        "ejecuta list_search_preferences para ver las "
                        "vigentes y luego propose_search_preference_removal "
                        "con la frase del concepto."
                    ),
                }
            )
        messages.append(_user_message(context))
        results_context = context.get("tool_results_context")
        if results_context:
            results_list = (
                list(results_context)
                if isinstance(results_context, list)
                else []
            )
            assistant_calls: list[dict[str, object]] = []
            for index, item in enumerate(results_list):
                if not isinstance(item, Mapping):
                    continue
                raw_args = item.get("args")
                args = dict(raw_args) if isinstance(raw_args, Mapping) else {}
                assistant_calls.append(
                    {
                        "id": f"umbral_call_{index}",
                        "type": "function",
                        "function": {
                            "name": str(item.get("tool", "")),
                            "arguments": json.dumps(args, ensure_ascii=False),
                        },
                    }
                )
            if assistant_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": assistant_calls,
                    }
                )
                for index, item in enumerate(results_list):
                    if not isinstance(item, Mapping):
                        continue
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": f"umbral_call_{index}",
                            "content": json.dumps(
                                item, ensure_ascii=False, default=str
                            ),
                        }
                    )
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": "Resultados de las tools ejecutadas:\n"
                        + json.dumps(
                            results_context, ensure_ascii=False, default=str
                        ),
                    }
                )
        try:
            result = deps.gateway.generate_structured(
                messages=tuple(messages),
                schema=deps.reply_schema,
                schema_version=deps.schema_version,
                prompt_version=deps.prompt_version,
                model_version=deps.model_version,
                tools=tuple(tool_specs) if tool_specs else None,
            )
        except Exception as exc:  # noqa: BLE001 - unknown provider failure
            _finish_node(
                recorder=recorder,
                node_name="generate_reply",
                graph_run_id=run_id,
                correlation_id=_uuid(context, "correlation_id"),
                started_at=node_started,
                finished_at=deps.clock(),
                status="interrupted",
                error_summary={
                    "code": "agent.provider_exception",
                    "kind": type(exc).__name__,
                },
            )
            raise
        deps.recorder.record_model_call(
            ModelCall(
                call_id=uuid4(),
                graph_run_id=run_id,
                model_version=result.model_version,
                prompt_version=deps.prompt_version,
                schema_version=deps.schema_version,
                status=result.status,
                correlation_id=_uuid(context, "correlation_id"),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
                error_code=result.error_code,
            )
        )
        raw_usage = context.get("token_usage")
        usage: Mapping[str, object] = (
            raw_usage if isinstance(raw_usage, Mapping) else {}
        )
        tool_calls: list[dict[str, object]] = []
        if result.status == "success" and result.content is not None:
            text = str(result.content.get("reply_text", ""))
            refs = result.content.get("refs")
            ref_list = [dict(item) for item in refs] if isinstance(refs, list) else []
            calls = result.content.get("tool_calls")
            if isinstance(calls, list):
                tool_calls = [
                    dict(item) for item in calls if isinstance(item, Mapping)
                ]
            if (
                not tool_calls
                and not state.get("tool_results")
                and isinstance(intent_data, Mapping)
            ):
                tool_calls = _fallback_tool_calls(
                    intent_data,
                    message_text=str(_context(state).get("user_message_text", "")),
                )
            if text:
                _emit_reply_chunks(
                    run_id=run_id,
                    text=text,
                    words=deps.reply_chunk_words,
                    emit=deps.sinks.emit,
                )
                context["generated_reply"] = {"text": text, "refs": ref_list}
            context["token_usage"] = _accumulate_usage(usage, result)
        else:
            errors.append({"code": result.error_code or "agent.generation_failed"})
        _finish_node(
            recorder=recorder,
            node_name="generate_reply",
            graph_run_id=run_id,
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="failed" if errors else "completed",
            error_summary=errors[-1] if errors else None,
        )
        return {"context": context, "errors": errors, "tool_calls": tool_calls}

    def _route_from_generate(state: AgentState) -> str:
        calls = state.get("tool_calls") or []
        if not calls:
            return "persist_reply"
        count = _as_int(_context(state).get("tool_loop_count"), 0)
        if count >= max_calls_per_turn:
            return "persist_reply"
        return "run_tools"

    def _run_tools(state: AgentState) -> dict[str, object]:
        context = _context(state)
        run_id = _uuid(context, "run_id")
        calls = state.get("tool_calls") or []
        count = _as_int(context.get("tool_loop_count"), 0)
        budget = max_calls_per_turn - count
        if budget <= 0 or not calls:
            context["tool_loop_exhausted"] = True
            return {"context": context, "tool_calls": []}
        intent_data = state.get("intent")
        allowed_tools = (
            tuple(str(item) for item in intent_data.get("allowed_tools", []))
            if isinstance(intent_data, Mapping)
            else ()
        )
        runnable = calls[:budget]
        results: list[dict[str, object]] = []
        for call in runnable:
            name = str(call.get("tool", ""))
            raw_args = call.get("args")
            args: Mapping[str, object] = (
                dict(raw_args) if isinstance(raw_args, Mapping) else {}
            )
            violations = validate_tool_calls(
                allowed_tools=allowed_tools,
                tool_calls=[{"tool": name, "args": args}],
            )
            if violations:
                results.append(
                    {
                        "tool": name,
                        "args": args,
                        "status": "error",
                        "result": None,
                        "error_code": violations[0].code,
                    }
                )
                continue
            args = _with_idempotency_key(
                executor=deps.tool_executor,
                name=name,
                args=args,
                session_id=_uuid(context, "session_id"),
                run_id=run_id,
            )
            args = _with_normalized_reason_keys(name, args)
            outcome = deps.tool_executor.execute(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                run_id=run_id,
                correlation_id=_uuid(context, "correlation_id"),
                name=name,
                args=args,
            )
            deps.sinks.emit(
                ToolActivity(run_id=run_id, tool=name, status=outcome.status)
            )
            results.append(
                {
                    "tool": name,
                    "args": args,
                    "status": outcome.status,
                    "result": dict(outcome.result) if outcome.result else None,
                    "error_code": outcome.error_code,
                }
            )
        context["tool_loop_count"] = count + len(runnable)
        context["tool_results_context"] = results
        if any(
            item.get("tool") in _PROPOSE_TOOLS
            and item.get("status") == "ok"
            and isinstance(item.get("result"), Mapping)
            for item in results
        ):
            context["proposal_created"] = True
        if any(
            item.get("tool") == "record_feedback"
            and item.get("status") == "ok"
            and _learning_proposal_id(item) is not None
            for item in results
        ):
            context["proposal_created"] = True
        existing = list(state.get("tool_results") or [])
        return {
            "context": context,
            "tool_calls": [],
            "tool_results": existing + results,
        }

    def _route_from_tools(state: AgentState) -> str:
        context = _context(state)
        if context.get("proposal_created"):
            return "require_confirmation"
        if context.get("tool_loop_exhausted"):
            return "persist_reply"
        return "generate_reply"

    def _require_confirmation(state: AgentState) -> dict[str, object]:
        context = _context(state)
        pending = state.get("pending_action")
        if pending is None:
            kind, proposal_id, diff, impact, expires_at = _waiting_proposal(state)
            operation = str(diff.get("operation", "propose"))
            decision_payload: dict[str, object]
            if kind == "preference_learning":
                learning = deps.preference_gateway.get_proposal(
                    owner_id=_uuid(context, "user_id"),
                    profile_id=_uuid(context, "search_profile_id"),
                    proposal_id=UUID(proposal_id),
                )
                state["pending_action"] = {
                    "kind": "preference",
                    "proposal_id": proposal_id,
                    "operation": "learning",
                }
                decision_payload = _payload_from_preference_proposal(learning)
            else:
                state["pending_action"] = {
                    "kind": kind,
                    "proposal_id": proposal_id,
                    "operation": operation,
                }
                decision_payload = {
                    "type": "proposal_decision",
                    "kind": kind,
                    "proposal_id": proposal_id,
                    "diff": diff,
                    "impact": impact,
                    "expires_at": expires_at,
                }
        else:
            pending_data = pending if isinstance(pending, Mapping) else {}
            kind = str(pending_data.get("kind", "profile"))
            proposal_id = str(pending_data.get("proposal_id", ""))
            if kind == "preference":
                proposal = deps.preference_gateway.get_proposal(
                    owner_id=_uuid(context, "user_id"),
                    profile_id=_uuid(context, "search_profile_id"),
                    proposal_id=UUID(proposal_id),
                )
                decision_payload = _payload_from_preference_proposal(proposal)
            else:
                proposal = deps.decision_gateway.get(
                    user_id=_uuid(context, "user_id"),
                    session_id=_uuid(context, "session_id"),
                    search_profile_id=_uuid(context, "search_profile_id"),
                    proposal_id=UUID(proposal_id),
                )
                decision_payload = _payload_from_proposal(proposal)
        decision = interrupt(decision_payload)
        context["decision"] = decision
        context["resume_decision"] = False
        _finish_node(
            recorder=recorder,
            node_name="require_confirmation",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=deps.clock(),
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context, "pending_action": state["pending_action"]}

    def _resolve_decision(state: AgentState) -> dict[str, object]:
        context = _context(state)
        decision = context.get("decision")
        if not isinstance(decision, Mapping):
            context["generated_reply"] = {
                "text": "No recibí una decisión válida para esa propuesta.",
                "refs": [],
            }
            return {"context": context}
        kind = decision.get("kind")
        pending = state.get("pending_action")
        pending_kind = (
            str(pending.get("kind", "profile"))
            if isinstance(pending, Mapping)
            else "profile"
        )
        proposal_id = (
            str(pending.get("proposal_id", "")) if isinstance(pending, Mapping) else ""
        )
        if kind == "edit":
            if pending_kind == "preference":
                context["generated_reply"] = {
                    "text": "No puedo editar una preferencia aún; "
                    "rechazala y proponé otra.",
                    "refs": [],
                }
                return {"context": context}
            change = decision.get("change")
            if not isinstance(change, Mapping):
                change = {}
            derived = deps.decision_gateway.derive(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                search_profile_id=_uuid(context, "search_profile_id"),
                proposal_id=UUID(proposal_id),
                change=dict(change),
                correlation_id=_uuid(context, "correlation_id"),
            )
            state["pending_action"] = {
                "kind": "profile",
                "proposal_id": str(derived.proposal_id),
            }
            context["resume_decision"] = True
            return {"context": context, "pending_action": state["pending_action"]}
        if kind == "approve":
            if pending_kind == "preference":
                operation = (
                    str(pending.get("operation", "propose"))
                    if isinstance(pending, Mapping)
                    else "propose"
                )
                try:
                    if operation == "remove":
                        deps.preference_gateway.confirm_preference_removal(
                            owner_id=_uuid(context, "user_id"),
                            profile_id=_uuid(context, "search_profile_id"),
                            proposal_id=UUID(proposal_id),
                            correlation_id=_uuid(context, "correlation_id"),
                            actor_kind="user",
                            actor_id=str(_uuid(context, "user_id")),
                        )
                    else:
                        deps.preference_gateway.confirm_proposal(
                            owner_id=_uuid(context, "user_id"),
                            profile_id=_uuid(context, "search_profile_id"),
                            proposal_id=UUID(proposal_id),
                            correlation_id=_uuid(context, "correlation_id"),
                            actor_kind="user",
                            actor_id=str(_uuid(context, "user_id")),
                        )
                except Exception as exc:  # noqa: BLE001 - typed at the boundary
                    context["generated_reply"] = {
                        "text": "No pude aplicar la preferencia. "
                        + _friendly_error(getattr(exc, "code", None)),
                        "refs": [],
                    }
                    return {"context": context}
                _record_preference_confirmation(
                    context=context,
                    proposal_id=proposal_id,
                    operation=operation,
                )
                context["generated_reply"] = {
                    "text": (
                        "Listo, quité la preferencia de tu radar."
                        if operation == "remove"
                        else (
                            "Listo, apliqué lo que aprendí a tu radar."
                            if operation == "learning"
                            else "Listo, apliqué la preferencia a tu radar."
                        )
                    ),
                    "refs": [],
                }
                return {"context": context}
            idempotency_key = str(decision.get("idempotency_key", ""))
            outcome = deps.tool_executor.execute(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                run_id=_uuid(context, "run_id"),
                correlation_id=_uuid(context, "correlation_id"),
                name="apply_search_profile_update",
                args={
                    "proposal_id": proposal_id,
                    "confirmation": True,
                    "idempotency_key": idempotency_key,
                },
                confirmation=True,
            )
            deps.sinks.emit(
                ToolActivity(
                    run_id=_uuid(context, "run_id"),
                    tool="apply_search_profile_update",
                    status=outcome.status,
                )
            )
            if outcome.status == "error":
                context["generated_reply"] = {
                    "text": "No pude aplicar el cambio. "
                    + _friendly_error(outcome.error_code),
                    "refs": [],
                }
            else:
                context["generated_reply"] = {
                    "text": "Listo, apliqué el cambio a tu radar.",
                    "refs": [],
                }
            return {"context": context}
        if kind == "reject":
            if pending_kind == "preference":
                try:
                    deps.preference_gateway.reject_proposal(
                        owner_id=_uuid(context, "user_id"),
                        profile_id=_uuid(context, "search_profile_id"),
                        proposal_id=UUID(proposal_id),
                        correlation_id=_uuid(context, "correlation_id"),
                        actor_id=str(_uuid(context, "user_id")),
                    )
                except Exception:  # noqa: BLE001 - typed at the boundary
                    context["generated_reply"] = {
                        "text": "No pude descartar la preferencia; "
                        "intentá de nuevo.",
                        "refs": [],
                    }
                    return {"context": context}
                context["generated_reply"] = {
                    "text": "Listo, descarté la preferencia propuesta.",
                    "refs": [],
                }
                return {"context": context}
            deps.decision_gateway.reject(
                user_id=_uuid(context, "user_id"),
                session_id=_uuid(context, "session_id"),
                search_profile_id=_uuid(context, "search_profile_id"),
                proposal_id=UUID(proposal_id),
                note=str(decision.get("reason") or ""),
                correlation_id=_uuid(context, "correlation_id"),
            )
            context["generated_reply"] = {
                "text": "Listo, descarté el cambio propuesto.",
                "refs": [],
            }
            return {"context": context}
        context["generated_reply"] = {
            "text": "No recibí una decisión válida para esa propuesta.",
            "refs": [],
        }
        return {"context": context}

    def _route_from_decision(state: AgentState) -> str:
        context = _context(state)
        if context.get("resume_decision"):
            return "require_confirmation"
        return "generate_reply"

    def _persist_reply(state: AgentState) -> dict[str, object]:
        context = _context(state)
        effects = dict(_effects(context))
        if _EFFECT_ASSISTANT_MESSAGE in effects:
            return {"context": context}
        reply = context.get("generated_reply")
        if not isinstance(reply, Mapping):
            return {"context": context}
        node_started = deps.clock()
        raw_refs = reply.get("refs", [])
        ref_list = [
            {"entity": str(item["entity"]), "id": str(item["id"])}
            for item in raw_refs
            if isinstance(item, Mapping)
        ]
        valid_refs, dropped = _validated_refs(state, ref_list, deps.reply_max_refs)
        text = str(reply.get("text", ""))
        if dropped and not text.rstrip().endswith((")", ".")):
            text = text.rstrip() + " (No pude verificar una de las referencias.)"
        message = deps.conversation.persist_assistant_message(
            user_id=_uuid(context, "user_id"),
            session_id=_uuid(context, "session_id"),
            text=text,
            refs=tuple(valid_refs),
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            now=deps.clock(),
        )
        effects[_EFFECT_ASSISTANT_MESSAGE] = _str(context, "run_id")
        context["effects_applied"] = effects
        context["assistant_message_id"] = str(message.message_id)
        _finish_node(
            recorder=recorder,
            node_name="persist_reply",
            graph_run_id=_uuid(context, "run_id"),
            correlation_id=_uuid(context, "correlation_id"),
            started_at=node_started,
            finished_at=deps.clock(),
            status="completed",
        )
        return {"context": context}

    builder = StateGraph(AgentState)
    builder.add_node("start", _start)
    builder.add_node("compile_intent", _compile_intent)
    builder.add_node("clarify", _clarify)
    builder.add_node("generate_reply", _generate_reply)
    builder.add_node("run_tools", _run_tools)
    builder.add_node("require_confirmation", _require_confirmation)
    builder.add_node("resolve_decision", _resolve_decision)
    builder.add_node("persist_reply", _persist_reply)
    builder.add_edge(START, "start")
    builder.add_edge("start", "compile_intent")
    builder.add_conditional_edges(
        "compile_intent",
        _route_from_compile,
        {
            "clarify": "clarify",
            "generate_reply": "generate_reply",
            "persist_reply": "persist_reply",
        },
    )
    builder.add_edge("clarify", "persist_reply")
    builder.add_conditional_edges(
        "generate_reply",
        _route_from_generate,
        {"run_tools": "run_tools", "persist_reply": "persist_reply"},
    )
    builder.add_conditional_edges(
        "run_tools",
        _route_from_tools,
        {
            "generate_reply": "generate_reply",
            "require_confirmation": "require_confirmation",
            "persist_reply": "persist_reply",
        },
    )
    builder.add_edge("require_confirmation", "resolve_decision")
    builder.add_conditional_edges(
        "resolve_decision",
        _route_from_decision,
        {
            "require_confirmation": "require_confirmation",
            "generate_reply": "generate_reply",
        },
    )
    builder.add_edge("persist_reply", END)
    compiled = builder.compile(checkpointer=saver)
    return AgentGraphV3(compiled=compiled, deps=deps)


def _waiting_proposal(
    state: AgentState,
) -> tuple[
    str, str, Mapping[str, object], Mapping[str, object], str
]:
    """Return (kind, proposal_id, diff, impact, expires_at) of the proposal
    created by a propose tool or a learning feedback in the current turn."""
    for item in state.get("tool_results") or []:
        if item.get("tool") in _PROPOSE_TOOLS and item.get("status") == "ok":
            result = item.get("result")
            if isinstance(result, Mapping):
                kind = (
                    "preference"
                    if item.get("tool") in _PREFERENCE_TOOLS
                    else "profile"
                )
                return (
                    kind,
                    str(result.get("proposal_id", "")),
                    _mapping_or_empty(result.get("diff")),
                    _mapping_or_empty(result.get("impact")),
                    str(result.get("expires_at", "")),
                )
        if (
            item.get("tool") == "record_feedback"
            and item.get("status") == "ok"
            and _learning_proposal_id(item) is not None
        ):
            return (
                "preference_learning",
                str(_learning_proposal_id(item)),
                {},
                {},
                "",
            )
    return ("", "", {}, {}, "")


def _fallback_tool_calls(
    intent_data: Mapping[str, object], *, message_text: str
) -> list[dict[str, object]]:
    """Recover one omitted proposal call from compiled parameters.

    The model may return useful structured parameters while forgetting the
    corresponding function call. This only selects a permitted proposal tool;
    validation and confirmation still happen in the existing executor.
    """
    if intent_data.get("intent") != "refinamiento":
        return []
    normalized_message = " ".join(message_text.casefold().split())
    if any(
        marker in normalized_message
        for marker in ("quit", "elimin", "sac", "remov", "aprend")
    ):
        return []
    raw_allowed = intent_data.get("allowed_tools")
    if not isinstance(raw_allowed, list):
        return []
    allowed = {str(item) for item in raw_allowed}
    parameters = intent_data.get("parameters")
    if not isinstance(parameters, list):
        return []

    for item in parameters:
        if not isinstance(item, Mapping):
            continue
        if item.get("key") == "preferencia":
            phrase = item.get("value")
            if (
                "propose_search_preference_update" in allowed
                and isinstance(phrase, str)
                and phrase.strip()
            ):
                return [
                    {
                        "tool": "propose_search_preference_update",
                        "args": {"preference": phrase},
                    }
                ]

    change: dict[str, str] = {}
    for item in parameters:
        if not isinstance(item, Mapping):
            continue
        key = item.get("key")
        value = item.get("value")
        if key in {"zona", "budget", "ambientes", "superficie"} and isinstance(
            value, str
        ):
            change[str(key)] = value
    if change and "propose_search_profile_update" in allowed:
        return [
            {
                "tool": "propose_search_profile_update",
                "args": {"change": change},
            }
        ]
    return []


def _payload_from_proposal(proposal: Proposal) -> dict[str, object]:
    return {
        "type": "proposal_decision",
        "kind": "profile",
        "proposal_id": str(proposal.proposal_id),
        "diff": dict(proposal.diff),
        "impact": dict(proposal.impact),
        "expires_at": proposal.expires_at.isoformat(),
    }


def _payload_from_preference_proposal(proposal: object) -> dict[str, object]:
    change = getattr(proposal, "change")
    concept_key = str(change.concept_key)
    polarity = str(change.polarity)
    diff: dict[str, object] = {
        "concept_key": concept_key,
        "polarity": polarity,
    }
    value = getattr(change, "value", None)
    if value is not None:
        diff["concept_value"] = value
    return {
        "type": "proposal_decision",
        "kind": "preference",
        "proposal_id": str(getattr(proposal, "proposal_id")),
        "diff": diff,
        "impact": {
            "concept_key": concept_key,
            "polarity": polarity,
            "will_recompute": True,
        },
        "expires_at": getattr(proposal, "expires_at").isoformat(),
    }


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _learning_proposal_id(item: Mapping[str, object]) -> str | None:
    """Extract the learning proposal id from a record_feedback result."""
    result = item.get("result")
    if not isinstance(result, Mapping):
        return None
    value = result.get("learning_proposal_id")
    return str(value) if value else None


def _with_normalized_reason_keys(
    name: str, args: Mapping[str, object]
) -> Mapping[str, object]:
    """Map natural reason labels to canonical quick-reason keys before the
    registry enum validation (0 LLM guessing, same seam as the vocabulary)."""
    if name != "record_feedback":
        return args
    raw = args.get("reason_keys")
    if not isinstance(raw, list) or not raw:
        return args
    from umbral.agent.tools.tools import _normalize_reason_keys

    updated = dict(args)
    updated["reason_keys"] = list(_normalize_reason_keys(raw))
    return updated


def _record_preference_confirmation(
    *,
    context: dict[str, object],
    proposal_id: str,
    operation: str,
) -> None:
    """Make the confirmed preference outcome visible to the reply model.

    ``resolve_decision`` confirms through the preference gateway (not the tool
    executor), so the generated reply would otherwise see no trace of the
    result and keep asking for confirmation; this appends a synthetic tool
    result that the next ``generate_reply`` round grounds on (R-14).
    """
    raw_results = context.get("tool_results_context")
    results: list[dict[str, object]] = (
        list(raw_results) if isinstance(raw_results, list) else []
    )
    results.append(
        {
            "tool": (
                "remove_search_preference"
                if operation == "remove"
                else "confirm_search_preference"
            ),
            "args": {"proposal_id": proposal_id, "operation": operation},
            "status": "ok",
            "result": {"operation": operation, "applied": True},
            "error_code": None,
        }
    )
    context["tool_results_context"] = results


def _with_idempotency_key(
    *,
    executor: ToolExecutor,
    name: str,
    args: Mapping[str, object],
    session_id: UUID,
    run_id: UUID,
) -> Mapping[str, object]:
    """Derive a server-side idempotency key when the model omitted it: replay
    semantics are a platform concern, never a model guess (R-05)."""
    current = args.get("idempotency_key")
    if isinstance(current, str) and current.strip():
        return args
    try:
        spec = executor.registry.get(name)
    except Exception:  # noqa: BLE001 - unknown tool stays as-is
        return args
    if not (spec.mutating and "idempotency_key" in spec.input_schema):
        return args
    updated = dict(args)
    listing_id = updated.get("listing_id")
    decision = updated.get("decision")
    if (
        name == "record_feedback"
        and isinstance(listing_id, str)
        and isinstance(decision, str)
    ):
        updated["idempotency_key"] = f"chat:{session_id}:{listing_id}:{decision}"
    else:
        updated["idempotency_key"] = f"chat:{session_id}:{name}:{run_id}:{uuid4()}"
    return updated


def _kind_label(value: object) -> str:
    """Render a tool arg kind (plain or enriched v2 entry) for the prompt,
    including the published description and enum so the model never guesses
    the vocabulary."""
    if isinstance(value, Mapping):
        kind = value.get("kind")
        if not isinstance(kind, str):
            return "?"
        label = kind
        parts: list[str] = []
        description = value.get("description")
        if isinstance(description, str) and description:
            parts.append(description)
        enum = value.get("enum")
        if isinstance(enum, list) and enum:
            parts.append("valores: " + ", ".join(str(item) for item in enum))
        if parts:
            label += " — " + "; ".join(parts)
        return label
    return str(value)


_REF_ENTITY_TYPES = frozenset({"listing", "criterion", "evidence_ref", "proposal"})


def _validated_refs(
    state: AgentState,
    refs: list[dict[str, str]],
    max_refs: int,
) -> tuple[list[dict[str, str]], int]:
    """Return (valid refs, dropped count): refs must appear in the turn's tool
    results and fit the cap; 0 invented or foreign refs persist (R-14)."""
    allowed = _tool_result_refs(state)
    valid: list[dict[str, str]] = []
    dropped = 0
    for ref in refs:
        entity = ref.get("entity")
        ref_id = ref.get("id")
        if entity not in _REF_ENTITY_TYPES or ref_id not in allowed.get(entity, set()):
            dropped += 1
            continue
        valid.append({"entity": entity, "id": ref_id})
    if len(valid) > max_refs:
        dropped += len(valid) - max_refs
        valid = valid[:max_refs]
    return valid, dropped


def _tool_result_refs(state: AgentState) -> dict[str, set[str]]:
    """Collect the valid product refs of the turn from the redacted tool
    results; the only refs a grounded reply may cite (FR-017)."""
    allowed: dict[str, set[str]] = {
        "listing": set(),
        "criterion": set(),
        "evidence_ref": set(),
        "proposal": set(),
    }
    for item in state.get("tool_results") or []:
        if not isinstance(item, Mapping) or item.get("status") != "ok":
            continue
        result = item.get("result")
        if not isinstance(result, Mapping):
            continue
        tool = item.get("tool")
        if tool == "find_matches":
            for raw in result.get("items", []):
                if isinstance(raw, Mapping) and raw.get("listing_id"):
                    allowed["listing"].add(str(raw["listing_id"]))
        elif tool == "explain_match":
            listing_id = result.get("listing_id")
            if listing_id:
                allowed["listing"].add(str(listing_id))
            for ref in result.get("evidence_refs", []):
                if isinstance(ref, Mapping) and ref.get("id"):
                    allowed["evidence_ref"].add(str(ref["id"]))
        elif tool == "get_listing_detail":
            listing_id = result.get("listing_id")
            if listing_id:
                allowed["listing"].add(str(listing_id))
        elif tool == "compare_listings":
            for raw in result.get("cells", []):
                if isinstance(raw, Mapping) and raw.get("listing_id"):
                    allowed["listing"].add(str(raw["listing_id"]))
        elif tool == _PROPOSE_TOOL:
            proposal_id = result.get("proposal_id")
            if proposal_id:
                allowed["proposal"].add(str(proposal_id))
        elif tool == _PREFERENCE_PROPOSE_TOOL:
            proposal_id = result.get("proposal_id")
            if proposal_id:
                allowed["proposal"].add(str(proposal_id))
        elif tool == _PREFERENCE_REMOVAL_TOOL:
            proposal_id = result.get("proposal_id")
            if proposal_id:
                allowed["proposal"].add(str(proposal_id))
    return allowed


def _emit_reply_chunks(
    *,
    run_id: UUID,
    text: str,
    words: int,
    emit: Callable[[RuntimeEvent], None],
) -> None:
    """Emit the reply as deterministic word-boundary fragments (R-07)."""
    parts = text.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    for part in parts:
        current.append(part)
        if len(current) >= max(1, words):
            chunks.append(" ".join(current))
            current = []
    if current:
        chunks.append(" ".join(current))
    for chunk in chunks:
        emit(ReplyFragment(run_id=run_id, delta=chunk))


def _friendly_error(error_code: str | None) -> str:
    return {
        "proposal.stale": "la propuesta quedó desactualizada; proponé de nuevo.",
        "proposal.expired": "la propuesta venció; proponé de nuevo.",
        "proposal.not_pending": "la propuesta ya fue usada o rechazada.",
        "feedback.not_found": "no encontré esa propuesta de preferencia.",
        "feedback.not_accessible": "esa propuesta no pertenece a tu radar.",
    }.get(error_code or "", "hubo un problema y no se aplicó ningún cambio.")


def build_input_state(
    *,
    run_id: UUID,
    session_id: UUID,
    user_id: UUID,
    correlation_id: UUID,
    user_message_text: str,
    schema_version: int = STATE_SCHEMA_VERSION,
    search_profile_id: str | None = None,
    client_message_id: str | None = None,
    user_message_context: Mapping[str, object] | None = None,
) -> AgentState:
    return build_initial_state(
        schema_version=schema_version,
        run_id=str(run_id),
        session_id=str(session_id),
        user_id=str(user_id),
        correlation_id=str(correlation_id),
        user_message_text=user_message_text,
        search_profile_id=search_profile_id,
        client_message_id=client_message_id,
        user_message_context=user_message_context,
    )


def _context(state: AgentState) -> dict[str, object]:
    return dict(state.get("context") or {})


def _effects(context: Mapping[str, object]) -> Mapping[str, object]:
    value = context.get("effects_applied")
    return value if isinstance(value, Mapping) else {}


def _user_message(context: Mapping[str, object]) -> Mapping[str, object]:
    return {"role": "user", "content": str(context.get("user_message_text", ""))}


def _uuid(context: Mapping[str, object], key: str) -> UUID:
    return UUID(str(context[key]))


def _str(context: Mapping[str, object], key: str) -> str:
    return str(context[key])


def _accumulate_usage(
    usage: Mapping[str, object], result: ModelResult
) -> dict[str, object]:
    input_tokens = result.input_tokens
    output_tokens = result.output_tokens
    return {
        "input": _as_int(usage.get("input"), 0) + input_tokens,
        "output": _as_int(usage.get("output"), 0) + output_tokens,
        "total": _as_int(usage.get("total"), 0) + input_tokens + output_tokens,
    }


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _finish_node(
    *,
    recorder: RunRecorder,
    node_name: str,
    graph_run_id: UUID,
    correlation_id: UUID,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    error_summary: Mapping[str, object] | None = None,
) -> None:
    recorder.record_node_run(
        NodeRun(
            node_run_id=uuid4(),
            graph_run_id=graph_run_id,
            node_name=node_name,
            node_kind="node",
            status=status,  # type: ignore[arg-type]
            correlation_id=correlation_id,
            started_at=started_at,
            finished_at=finished_at,
            error_summary=error_summary,
        )
    )
