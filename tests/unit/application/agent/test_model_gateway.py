"""ModelGateway port and fake unit tests (foundational, R-05)."""

from __future__ import annotations

import pytest

from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

_REPLY_SCHEMA = {"reply_text": {"kind": "string"}, "refs": {"kind": "list"}}


def test_fake_gateway_returns_structured_reply_and_records_call() -> None:
    gateway = FakeModelGateway(model_version="local-fake")
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_REPLY_SCHEMA,
        schema_version="reply-v1",
        prompt_version="agent-chat-v1",
        model_version="local-fake",
    )
    assert result.status == "success"
    assert result.content is not None
    assert "reply_text" in result.content
    assert result.model_version == "local-fake"
    assert result.total_tokens == result.input_tokens + result.output_tokens
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["prompt_version"] == "agent-chat-v1"


def test_fake_gateway_can_simulate_provider_crash() -> None:
    gateway = FakeModelGateway(raise_on_call=1)
    with pytest.raises(RuntimeError):
        gateway.generate_structured(
            messages=({"role": "user", "content": "hola"},),
            schema=_REPLY_SCHEMA,
            schema_version="reply-v1",
            prompt_version="agent-chat-v1",
            model_version="local-fake",
        )
