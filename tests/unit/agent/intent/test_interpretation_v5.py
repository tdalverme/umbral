"""Unit tests for the V5 structured interpretation compiler."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from umbral.agent.intent.v5 import (
    InterpretationCompilerV5,
    InterpretationContractFailed,
)
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.v5.contracts import (
    EvidenceSpan,
    PendingActionV5,
    Query,
    RecordFeedback,
    TurnContextV5,
    TurnInterpretationV5,
)

CORRELATION_ID = "correlation:1"


def _context(
    *,
    listing_ref: str | None = "listing:13",
    desire_ref: str | None = "desire:1",
    pending_ref: str | None = None,
) -> TurnContextV5:
    return TurnContextV5(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=(
            PendingActionV5(pending_ref=pending_ref) if pending_ref else None
        ),
        focused_entity=None,
        verified_listing_refs=(listing_ref,) if listing_ref else (),
        allowed_capabilities=(
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
        ),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id="correlation:1",
    )


class _FakeGateway:
    def __init__(self, reply: Mapping[str, object] | None = None) -> None:
        self._reply = reply or {"acts": []}
        self.calls: list[dict[str, object]] = []

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Any = None,
    ) -> ModelResult:
        self.calls.append(
            {
                "messages": list(messages),
                "schema": dict(schema),
                "schema_version": schema_version,
                "prompt_version": prompt_version,
                "model_version": model_version,
            }
        )
        return ModelResult(
            content=dict(self._reply),
            model_version=model_version,
            status="success",
            latency_ms=1,
        )


def _span(start: int, end: int, text: str) -> dict[str, object]:
    return {"start": start, "end": end, "text": text}


def _act(kind: str, **fields: object) -> dict[str, object]:
    message = "¿Qué opinás?"
    return {
        "act_id": "a1",
        "kind": kind,
        "confidence": 0.9,
        "evidence_spans": [_span(0, len(message), message)],
        **fields,
    }


def _compiler(gateway: ModelGateway) -> InterpretationCompilerV5:
    return InterpretationCompilerV5(
        gateway=gateway,
        schema={"type": "object"},
        prompt_version="interpretation-v5",
        model_version="gpt-4.1-mini",
    )


def _interpret(
    gateway: ModelGateway,
    *,
    message: str = "¿Qué opinás?",
    context: TurnContextV5 | None = None,
) -> TurnInterpretationV5:
    return _compiler(gateway).interpret(
        message_text=message,
        context=context if context is not None else _context(),
        correlation_id=CORRELATION_ID,
    )


def test_compiler_passes_authorized_context_and_labels_untrusted_content() -> None:
    message = "¿Qué opinás?"
    gateway = _FakeGateway(
        {"acts": [_act("query", query_text=message)]}
    )
    context = _context()

    result = _compiler(gateway).interpret(
        message_text=message, context=context, correlation_id=CORRELATION_ID
    )

    messages = cast(list[dict[str, object]], gateway.calls[0]["messages"])
    system = cast(str, messages[0]["content"])
    assert "AUTHORIZED_CONTEXT" in system
    assert "UNTRUSTED_CONTENT" in system
    assert result.acts == (
        Query(
            act_id="a1",
            confidence=0.9,
            evidence_spans=(
                EvidenceSpan(start=0, end=len(message), text=message),
            ),
            query_text=message,
        ),
    )


def test_compiler_rejects_listing_ref_absent_from_context() -> None:
    gateway = _FakeGateway(
        {
            "acts": [
                _act(
                    "record_feedback",
                    listing_ref="listing:not-authorized",
                    feedback_type="dislike",
                )
            ]
        }
    )

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)


def test_compiler_rejects_missing_evidence() -> None:
    gateway = _FakeGateway(
        {
            "acts": [
                {
                    "act_id": "a1",
                    "kind": "query",
                    "confidence": 0.9,
                    "query_text": "x",
                }
            ]
        }
    )

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)


def test_compiler_rejects_evidence_mismatching_user_message() -> None:
    gateway = _FakeGateway(
        {
            "acts": [
                {
                    "act_id": "a1",
                    "kind": "query",
                    "confidence": 0.9,
                    "evidence_spans": [_span(0, 5, "texto falso")],
                    "query_text": "x",
                }
            ]
        }
    )

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)


def test_compiler_rejects_duplicate_act_ids() -> None:
    gateway = _FakeGateway(
        {
            "acts": [
                _act("query", act_id="a1", query_text="x"),
                _act("query", act_id="a1", query_text="y"),
            ]
        }
    )

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)


def test_compiler_rejects_more_than_six_acts() -> None:
    acts = [_act("query", act_id=f"a{i}", query_text="x") for i in range(7)]
    gateway = _FakeGateway({"acts": acts})

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)


def test_compiler_rejects_unknown_kind() -> None:
    gateway = _FakeGateway({"acts": [_act("delete_account")]})

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)


def test_compiler_accepts_feedback_with_verified_focus_listing() -> None:
    gateway = _FakeGateway(
        {
            "acts": [
                _act(
                    "record_feedback",
                    listing_ref="listing:13",
                    feedback_type="dislike",
                    raw_text="No me gusta",
                )
            ]
        }
    )

    message = "¿Qué opinás?"
    result = _compiler(gateway).interpret(
        message_text=message, context=_context(), correlation_id=CORRELATION_ID
    )

    assert result.acts == (
        RecordFeedback(
            act_id="a1",
            confidence=0.9,
            evidence_spans=(
                EvidenceSpan(start=0, end=len(message), text=message),
            ),
            listing_ref="listing:13",
            feedback_type="dislike",
            raw_text="No me gusta",
        ),
    )


def test_compiler_rejects_pending_ref_absent_from_context() -> None:
    gateway = _FakeGateway(
        {
            "acts": [
                _act("resolve_pending", pending_ref="pending:99", decision="approve")
            ]
        }
    )

    with pytest.raises(InterpretationContractFailed):
        _interpret(gateway)
