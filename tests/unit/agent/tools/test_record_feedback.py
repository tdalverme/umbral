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
