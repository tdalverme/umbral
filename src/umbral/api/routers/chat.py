"""Chat streaming HTTP contract (UM-H4-021, R-08).

SSE transport over the runtime events; typed errors (problem+json) and the
``product.chat.*`` access actions. The web reaches this only through the BFF.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from umbral.agent.events import (
    BudgetWarning,
    InterruptWaiting,
    ReplyFragment,
    RunCompleted,
    RunFailed,
    RunInterrupted,
    RunStarted,
    RuntimeEvent,
    ToolActivity,
)
from umbral.agent.runtime import ChatRuntime
from umbral.application.agent.contracts import (
    AgentBudgetExhausted,
    AgentRateLimitExceeded,
    AgentRunNotFound,
)
from umbral.application.agent.tools.contracts import ProposalError
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.contracts import (
    ChatError,
    ChatMessageTooLong,
    ChatSessionNotActive,
    ChatSessionNotFound,
)
from umbral.application.chat.service import ChatService
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import RadarError

router = APIRouter(prefix="/api/v1", tags=["chat"])

_dependencies: Any = None


def configure_chat_routes(dependencies: Any) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> Any:
    if _dependencies is None:
        raise RuntimeError("chat routes were not configured")
    return _dependencies


def _chat() -> ChatService:
    service = _deps().chat
    if service is None:
        raise RuntimeError("chat service was not configured")
    return cast(ChatService, service)


def _runtime() -> ChatRuntime:
    runtime = _deps().agent_runtime
    if runtime is None:
        raise RuntimeError("agent runtime was not configured")
    return cast(ChatRuntime, runtime)


def _proposals() -> SearchProfileUpdateProposals:
    proposals = _deps().proposals
    if proposals is None:
        raise RuntimeError("proposals service was not configured")
    return cast(SearchProfileUpdateProposals, proposals)


def _graph_runs() -> Any:
    runs = _deps().graph_runs
    if runs is None:
        raise RuntimeError("graph run repository was not configured")
    return runs


def _correlation(request: Request) -> UUID | None:
    value = request.headers.get("X-Correlation-ID")
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _principal(request: Request) -> CurrentPrincipal:
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    return cast(
        CurrentPrincipal,
        _deps().access_control.authorize(
            token,
            action="auth.session.read",
            resource_owner_id=None,
            now=datetime.now(timezone.utc),
            correlation_id=_correlation(request),
        ),
    )


def _require(request: Request, action: str) -> CurrentPrincipal:
    principal = _principal(request)
    token = request.cookies.get(_deps().settings.session_cookie_name) or ""
    return cast(
        CurrentPrincipal,
        _deps().access_control.authorize(
            token,
            action=action,
            resource_owner_id=principal.user_id,
            now=datetime.now(timezone.utc),
            correlation_id=_correlation(request),
        ),
    )


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://umbral.invalid/problems/{code}",
            "title": "Chat",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _error_problem(request: Request, error: Exception) -> JSONResponse | None:
    code = getattr(error, "code", None)
    if isinstance(error, ChatSessionNotFound):
        return _problem(request, 404, "chat.session_not_found", str(error))
    if isinstance(error, ChatSessionNotActive):
        return _problem(request, 409, "chat.session_not_active", str(error))
    if isinstance(error, ChatMessageTooLong):
        return _problem(request, 422, "chat.message_too_long", str(error))
    if isinstance(error, ChatError):
        return _problem(request, 409, code or "chat.error", str(error))
    if isinstance(error, AgentRunNotFound):
        return _problem(request, 404, "agent.run_not_found", str(error))
    if isinstance(error, AgentBudgetExhausted):
        return _problem(request, 429, "agent.budget_exhausted", str(error))
    if isinstance(error, AgentRateLimitExceeded):
        return _problem(request, 429, "agent.rate_limit_exceeded", str(error))
    if code == "agent.state_incompatible":
        return _problem(request, 409, "agent.state_incompatible", str(error))
    if isinstance(error, ProposalError):
        return _problem(request, 409, code or "proposal.error", str(error))
    if isinstance(error, RadarError):
        return _problem(request, 403, code or "radar.not_accessible", str(error))
    return None


def _ssenline(event_type: str, sequence: int, payload: Mapping[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_type}\nid: {sequence}\ndata: {data}\n\n"


def _serialize_event(event: RuntimeEvent, sequence: int) -> str | None:
    if isinstance(event, RunStarted):
        return _ssenline(
            "chat.run_started",
            sequence,
            {"run_id": str(event.run_id), "session_id": str(event.session_id)},
        )
    if isinstance(event, ReplyFragment):
        return _ssenline(
            "chat.reply_fragment",
            sequence,
            {"run_id": str(event.run_id), "delta": event.delta},
        )
    if isinstance(event, ToolActivity):
        return _ssenline(
            "chat.tool_activity",
            sequence,
            {"run_id": str(event.run_id), "tool": event.tool, "status": event.status},
        )
    if isinstance(event, InterruptWaiting):
        return _ssenline(
            "chat.interrupt_waiting",
            sequence,
            {"run_id": str(event.run_id), "interrupt": dict(event.interrupt)},
        )
    if isinstance(event, RunCompleted):
        return _ssenline(
            "chat.run_completed",
            sequence,
            {
                "run_id": str(event.run_id),
                "message_id": str(event.message_id) if event.message_id else "",
            },
        )
    if isinstance(event, RunFailed):
        return _ssenline(
            "chat.run_failed",
            sequence,
            {"run_id": str(event.run_id), "error_code": event.error_code},
        )
    if isinstance(event, RunInterrupted):
        return _ssenline(
            "chat.run_interrupted",
            sequence,
            {"run_id": str(event.run_id)},
        )
    if isinstance(event, BudgetWarning):
        return _ssenline(
            "chat.budget_warning",
            sequence,
            {
                "session_id": str(event.session_id),
                "ratio": float(event.ratio),
            },
        )
    return None


def _stream_turn(
    *,
    user_id: UUID,
    session_id: UUID,
    text: str,
    correlation_id: UUID,
    resume: bool = False,
    decision: Mapping[str, object] | None = None,
    client_message_id: UUID | None = None,
    context: Mapping[str, object] | None = None,
) -> StreamingResponse:
    """Run the turn in a background thread and stream SSE events."""
    events: queue.Queue[str | None] = queue.Queue()
    counter = {"n": 0}

    def worker() -> None:
        def emit(event: RuntimeEvent) -> None:
            serialized = _serialize_event(event, counter["n"])
            counter["n"] += 1
            if serialized is not None:
                events.put(serialized)

        _runtime().run_turn(
            user_id=user_id,
            session_id=session_id,
            text=text,
            correlation_id=correlation_id,
            resume=resume,
            decision=decision,
            consumer=emit,
            client_message_id=client_message_id,
            context=context,
        )
        events.put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def generate() -> Any:
        while True:
            item = await run_in_threadpool(events.get)
            if item is None:
                break
            yield item

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@dataclass(frozen=True, slots=True)
class _SessionResponse:
    session_id: UUID
    search_profile_id: UUID
    status: str


def _session_payload(session: Any) -> dict[str, object]:
    return {
        "session_id": str(session.session_id),
        "search_profile_id": str(session.search_profile_id),
        "status": session.status,
    }


@router.post("/chat/sessions", operation_id="createSession")
def create_session(request: Request, body: dict[str, Any]) -> JSONResponse:
    principal = _require(request, "product.chat.session.create")
    search_profile_id = UUID(str(body.get("search_profile_id", "")))
    session = _chat().create_session(
        user_id=principal.user_id,
        search_profile_id=search_profile_id,
        correlation_id=_correlation(request) or uuid4(),
    )
    return JSONResponse(_session_payload(session), status_code=201)


@router.get("/chat/sessions", operation_id="listChatSessions")
def list_sessions(
    request: Request, search_profile_id: str | None = None
) -> JSONResponse:
    principal = _require(request, "product.chat.session.read")
    if search_profile_id is None:
        return JSONResponse({"items": []})
    sessions = _chat().list_sessions(
        user_id=principal.user_id,
        search_profile_id=UUID(search_profile_id),
    )
    return JSONResponse(
        {"items": [_session_payload(session) for session in sessions]}
    )


@router.get("/chat/sessions/{session_id}", operation_id="getChatSession")
def get_session(request: Request, session_id: UUID) -> JSONResponse:
    principal = _require(request, "product.chat.session.read")
    try:
        session = _chat().get_session(user_id=principal.user_id, session_id=session_id)
    except ChatError as error:
        response = _error_problem(request, error)
        assert response is not None
        return response
    return JSONResponse(_session_payload(session))


@router.get(
    "/chat/sessions/{session_id}/messages", operation_id="listChatSessionMessages"
)
def list_messages(
    request: Request,
    session_id: UUID,
    limit: int = 50,
    before_message_id: str | None = None,
) -> JSONResponse:
    principal = _require(request, "product.chat.session.read")
    try:
        messages = _chat().list_history(
            user_id=principal.user_id, session_id=session_id
        )
    except ChatError as error:
        response = _error_problem(request, error)
        assert response is not None
        return response
    items = [
        {
            "message_id": str(message.message_id),
            "role": message.role,
            "content": dict(message.content),
            "created_at": message.created_at.isoformat(),
        }
        for message in messages
    ]
    return JSONResponse({"items": items})


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=None,
    operation_id="sendChatMessage",
)
def send_message(
    request: Request, session_id: UUID, body: dict[str, Any]
) -> StreamingResponse | JSONResponse:
    principal = _require(request, "product.chat.message.write")
    text = str(body.get("text", ""))
    active = _graph_runs().active_for_session(session_id)
    if active is not None and active.status == "interrupted":
        return _problem(
            request,
            409,
            "chat.decision_pending",
            "La conversación espera tu decisión sobre una propuesta.",
        )
    client_message_id = body.get("client_message_id")
    context = body.get("context")
    return _stream_turn(
        user_id=principal.user_id,
        session_id=session_id,
        text=text,
        correlation_id=_correlation(request) or uuid4(),
        client_message_id=(
            UUID(str(client_message_id)) if client_message_id else None
        ),
        context=context if isinstance(context, dict) else None,
    )


@router.post(
    "/chat/sessions/{session_id}/resume",
    response_model=None,
    operation_id="resumeChatSession",
)
def resume_session(
    request: Request, session_id: UUID
) -> StreamingResponse | JSONResponse:
    principal = _require(request, "product.chat.message.write")
    active = _graph_runs().active_for_session(session_id)
    if active is None:
        return _problem(
            request, 409, "agent.no_pending_interrupt", "No hay ejecución que reanudar."
        )
    return _stream_turn(
        user_id=principal.user_id,
        session_id=session_id,
        text="",
        correlation_id=_correlation(request) or uuid4(),
        resume=True,
    )


@router.post(
    "/chat/sessions/{session_id}/runs/{run_id}/decision",
    response_model=None,
    operation_id="decideChatRun",
)
def decide_run(
    request: Request, session_id: UUID, run_id: UUID, body: dict[str, Any]
) -> StreamingResponse | JSONResponse:
    principal = _require(request, "product.chat.decision.write")
    run = _graph_runs().get(run_id)
    if run is None or run.session_id != session_id:
        return _problem(request, 404, "agent.run_not_found", "No existe esa ejecución.")
    if run.status != "interrupted":
        return _problem(
            request,
            409,
            "agent.no_pending_interrupt",
            "La ejecución no espera decisión.",
        )
    decision = dict(body)
    return _stream_turn(
        user_id=principal.user_id,
        session_id=session_id,
        text="",
        correlation_id=_correlation(request) or uuid4(),
        resume=True,
        decision=decision,
    )


@router.get(
    "/search-profiles/{search_profile_id}/update-proposals",
    operation_id="listUpdateProposals",
)
def list_update_proposals(
    request: Request, search_profile_id: UUID, state: str = "pending"
) -> JSONResponse:
    principal = _require(request, "product.search_profile.read")
    listings = _proposals().list(
        user_id=principal.user_id,
        search_profile_id=search_profile_id,
        state=state,
    )
    return JSONResponse(
        {
            "items": [
                {
                    "proposal_id": str(item.proposal_id),
                    "session_id": str(item.session_id),
                    "search_profile_id": str(item.search_profile_id),
                    "state": item.state,
                    "diff": dict(item.diff),
                    "impact": dict(item.impact),
                    "expires_at": item.expires_at.isoformat(),
                    "rejection_reason": item.rejection_reason,
                    "rejection_note": item.rejection_note,
                    "superseded_by_proposal_id": (
                        str(item.superseded_by_proposal_id)
                        if item.superseded_by_proposal_id
                        else None
                    ),
                    "waiting_run_id": (
                        str(item.waiting_run_id) if item.waiting_run_id else None
                    ),
                }
                for item in listings
            ]
        }
    )
