"""Managed model gateway unit tests (US4, SC-004)."""

from __future__ import annotations

import httpx

from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway

_REPLY_SCHEMA = {"reply_text": {"kind": "string"}, "refs": {"kind": "list"}}
_INTENT_SCHEMA = {
    "intent": "string",
    "parameters": [{"key": "string", "value": "string", "confidence": "number"}],
    "high_impact_missing": ["string"],
    "contradictions": [
        {"key": "string", "current_value": "string", "requested": "string"}
    ],
}
_OK_BODY = {
    "content": {"reply_text": "hola", "refs": []},
    "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
}


def _gateway(
    transport: httpx.MockTransport, *, max_retries: int = 2
) -> ManagedModelGateway:
    return ManagedModelGateway(
        endpoint="https://provider.invalid/v1",
        api_key="test",
        model="local",
        timeout_seconds=1.0,
        max_retries=max_retries,
        http_client=httpx.Client(transport=transport),
        sleep=lambda _seconds: None,
    )


def test_success_returns_validated_content_and_usage() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OK_BODY)

    transport = httpx.MockTransport(handler)
    gateway = _gateway(transport)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_REPLY_SCHEMA,
        schema_version="reply-v1",
        prompt_version="agent-chat-v1",
        model_version="m1",
    )
    assert result.status == "success"
    assert result.content == {"reply_text": "hola", "refs": []}
    assert result.total_tokens == 8
    assert result.error_code is None


def test_intent_shaped_output_is_accepted() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": {
                    "intent": "consulta",
                    "parameters": [],
                    "high_impact_missing": [],
                    "contradictions": [],
                },
                "usage": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            },
        )

    transport = httpx.MockTransport(handler)
    gateway = _gateway(transport)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_INTENT_SCHEMA,
        schema_version="intent-v3",
        prompt_version="agent-intent-v1",
        model_version="m1",
    )
    assert result.status == "success"
    expected = {
        "intent": "consulta",
        "parameters": [],
        "high_impact_missing": [],
        "contradictions": [],
    }
    assert result.content == expected
    assert result.error_code is None


def test_intent_shaped_empty_content_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": {}, "usage": {}})

    gateway = _gateway(httpx.MockTransport(handler), max_retries=1)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_INTENT_SCHEMA,
        schema_version="intent-v3",
        prompt_version="agent-intent-v1",
        model_version="m1",
    )
    assert result.status == "invalid_output"
    assert result.error_code == "agent.invalid_output"


def test_invalid_output_is_rejected_after_bounded_retries() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": {"reply_text": "", "refs": []}})

    gateway = _gateway(httpx.MockTransport(handler), max_retries=1)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_REPLY_SCHEMA,
        schema_version="reply-v1",
        prompt_version="agent-chat-v1",
        model_version="m1",
    )
    assert result.status == "invalid_output"
    assert result.error_code == "agent.invalid_output"


def test_timeout_exhausts_bounded_retry() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=_request)

    gateway = _gateway(httpx.MockTransport(handler), max_retries=1)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_REPLY_SCHEMA,
        schema_version="reply-v1",
        prompt_version="agent-chat-v1",
        model_version="m1",
    )
    assert result.status == "timeout"
    assert result.error_code == "agent.timeout"


def test_transient_5xx_becomes_typed_error_after_retries() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    gateway = _gateway(httpx.MockTransport(handler), max_retries=1)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_REPLY_SCHEMA,
        schema_version="reply-v1",
        prompt_version="agent-chat-v1",
        model_version="m1",
    )
    assert result.status == "error"
    assert result.error_code == "provider.http_500"


def test_4xx_is_a_typed_permanent_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={})

    gateway = _gateway(httpx.MockTransport(handler), max_retries=1)
    result = gateway.generate_structured(
        messages=({"role": "user", "content": "hola"},),
        schema=_REPLY_SCHEMA,
        schema_version="reply-v1",
        prompt_version="agent-chat-v1",
        model_version="m1",
    )
    assert result.status == "error"
    assert result.error_code == "provider.http_error"
