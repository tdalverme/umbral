"""Chat streaming events contract conformance (R-07, T031)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STREAM_CONTRACT = json.loads(
    (ROOT / "contracts" / "chat" / "v1" / "streaming-events-v1.json").read_text(
        encoding="utf-8"
    )
)


def test_streaming_contract_declares_all_event_types() -> None:
    assert STREAM_CONTRACT["registry_version"] == "chat-streaming-events-v1"
    assert STREAM_CONTRACT["contract_version"] == "1"
    assert STREAM_CONTRACT["transport"] == "text/event-stream"
    names = {event["name"] for event in STREAM_CONTRACT["events"]}
    assert names == {
        "chat.run_started",
        "chat.reply_fragment",
        "chat.tool_activity",
        "chat.interrupt_waiting",
        "chat.run_completed",
        "chat.run_failed",
        "chat.run_interrupted",
        "chat.budget_warning",
    }


def test_budget_warning_payload_declares_session_and_ratio() -> None:
    warning = next(
        event
        for event in STREAM_CONTRACT["events"]
        if event["name"] == "chat.budget_warning"
    )
    assert "session_id" in warning["payload"]
    assert "ratio" in warning["payload"]


def test_streaming_contract_envelope() -> None:
    envelope = STREAM_CONTRACT["envelope"]
    assert envelope["event"] == "<type>"
    assert envelope["id"] == "<sequence>"
    assert envelope["data"] == "<json payload>"


def test_interrupt_waiting_payload_declares_proposal_fields() -> None:
    interrupt = next(
        event
        for event in STREAM_CONTRACT["events"]
        if event["name"] == "chat.interrupt_waiting"
    )
    interrupt_payload = interrupt["payload"]["interrupt"]
    assert interrupt_payload["type"] == "proposal_decision"
    assert "proposal_id" in interrupt_payload
    assert "diff" in interrupt_payload
    assert "impact" in interrupt_payload
    assert "expires_at" in interrupt_payload
