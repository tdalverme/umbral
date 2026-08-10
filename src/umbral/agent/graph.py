"""Topology v1 graph for the conversational runtime (UM-H4-002, FR-016).

The graph is provider-agnostic: model gateway, conversation sink, run
recorder and checkpointer arrive via the constructor (the agent layer never
imports infrastructure, R-03). Effects are deduplicated through the
``context.effects_applied`` ledger so a resume never repeats them (FR-014).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph

from umbral.agent.events import ReplyFragment, RuntimeEvent
from umbral.agent.state import (
    STATE_SCHEMA_VERSION,
    AgentState,
    build_initial_state,
)
from umbral.application.agent.contracts import ModelCall, ModelResult, NodeRun
from umbral.application.agent.ports import ModelGateway, RunRecorder
from umbral.application.chat.ports import ConversationGateway

TOPOLOGY_VERSION = 1

_EFFECT_USER_MESSAGE = "user_message"
_EFFECT_ASSISTANT_MESSAGE = "assistant_message"


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


def build_input_state(
    *,
    run_id: UUID,
    session_id: UUID,
    user_id: UUID,
    correlation_id: UUID,
    user_message_text: str,
    schema_version: int = STATE_SCHEMA_VERSION,
) -> AgentState:
    return build_initial_state(
        schema_version=schema_version,
        run_id=str(run_id),
        session_id=str(session_id),
        user_id=str(user_id),
        correlation_id=str(correlation_id),
        user_message_text=user_message_text,
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
