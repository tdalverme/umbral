# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""record_feedback tool tests (FR-019/FR-020, T038)."""

from __future__ import annotations

from uuid import UUID

from tests.support.tools import build_executor, call_tool, payload


def test_record_feedback_like_returns_learning_proposal() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "record_feedback",
        {
            "listing_id": str(UUID(int=70)),
            "decision": "like",
            "reason_keys": ["balcony_wanted"],
            "idempotency_key": "k-1",
        },
    )
    assert result.status == "ok"
    assert result.result is not None
    assert payload(result)["noop"] is False
    assert payload(result)["learning_proposal_id"] is not None
    assert services.feedback.calls[0]["event_type"] == "like"
    assert services.feedback.calls[0]["reason_keys"] == ("balcony_wanted",)


def test_record_feedback_dislike_has_no_proposal() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "record_feedback",
        {
            "listing_id": str(UUID(int=70)),
            "decision": "dislike",
            "reason_keys": [],
            "idempotency_key": "k-2",
        },
    )
    assert result.status == "ok"
    assert payload(result)["learning_proposal_id"] is None


def test_record_feedback_rejects_out_of_contract_types() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "record_feedback",
        {
            "listing_id": str(UUID(int=70)),
            "decision": "save",
            "reason_keys": [],
            "idempotency_key": "k-3",
        },
    )
    assert result.status == "error"
    assert result.error_code == "tool.args_invalid"


def test_record_feedback_forwards_concept_feedback_to_the_service() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "record_feedback",
        {
            "listing_id": str(UUID(int=70)),
            "decision": "dislike",
            "reason_keys": [],
            "concept_feedback": [
                {
                    "concept_key": "tipo_cocina",
                    "polarity": "negative",
                    "strength": "strong",
                    "confidence": 0.85,
                }
            ],
            "idempotency_key": "k-4",
        },
    )
    assert result.status == "ok"
    assert payload(result)["event_id"] is not None
    call = services.feedback.calls[0]
    assert call["concept_feedback"][0]["concept_key"] == "tipo_cocina"
    assert call["concept_feedback"][0]["strength"] == "strong"
    assert call["concept_feedback"][0]["confidence"] == 0.85


def test_record_feedback_drops_malformed_concept_feedback_entries() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "record_feedback",
        {
            "listing_id": str(UUID(int=70)),
            "decision": "dislike",
            "reason_keys": [],
            "concept_feedback": [
                {
                    "concept_key": "tipo_cocina",
                    "polarity": "negative",
                    "strength": "medium",
                },
                "basura",
                {
                    "concept_key": "balcon",
                    "polarity": "positive",
                    "strength": "low",
                    "confidence": 0.4,
                },
            ],
            "idempotency_key": "k-5",
        },
    )
    assert result.status == "ok"
    call = services.feedback.calls[0]
    assert len(call["concept_feedback"]) == 1
    assert call["concept_feedback"][0]["concept_key"] == "balcon"


def test_record_feedback_forwards_free_feedback_when_provided() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "record_feedback",
        {
            "listing_id": str(UUID(int=70)),
            "decision": "dislike",
            "reason_keys": [],
            "free_feedback": "la cocina es chica e integrada",
            "idempotency_key": "k-6",
        },
    )
    assert result.status == "ok"
    assert (
        services.feedback.calls[0]["free_feedback"]
        == "la cocina es chica e integrada"
    )
