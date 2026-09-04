"""Managed model gateway server conformance tests (ADR 0001)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from umbral.infrastructure.agent.model_gateway.server import (
    _strict_compatible,
    _translate_schema,
    create_app,
)

_INTENT_PAYLOAD = {
    "model": "gpt-4.1-mini",
    "model_version": "gpt-4.1-mini",
    "prompt_version": "agent-intent-v1",
    "schema_version": "intent-v3",
    "schema": {
        "intent": "string",
        "parameters": [{"key": "string", "value": "string", "confidence": "number"}],
        "high_impact_missing": ["string"],
        "contradictions": [
            {"key": "string", "current_value": "string", "requested": "string"}
        ],
        "_intents": [
            {"name": "consulta", "description": "preguntas de solo lectura"},
            {"name": "fuera_de_alcance", "description": "fuera de alcance"},
        ],
    },
    "messages": [{"role": "user", "content": "hola"}],
}

_OK_CONTENT = {
    "intent": "consulta",
    "parameters": [],
    "high_impact_missing": [],
    "contradictions": [],
}


def _client(
    handler: object | None = None,
    *,
    shared_key: str | None = None,
    api_key: str = "test-openai-key",
) -> tuple[TestClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler_fn(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if handler is None:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(_OK_CONTENT)}}],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 5,
                        "total_tokens": 8,
                    },
                },
            )
        if callable(handler):
            response = handler(request)
            assert isinstance(response, httpx.Response)
            return response
        raise AssertionError("handler must be callable")

    transport = httpx.MockTransport(handler_fn)
    app = create_app(
        openai_api_key=api_key,
        shared_key=shared_key,
        http_client=httpx.Client(transport=transport),
    )
    return TestClient(app), requests


def test_valid_request_returns_content_and_usage() -> None:
    client, requests = _client()
    response = client.post("/v1/structured", json=_INTENT_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == _OK_CONTENT
    assert body["usage"] == {
        "input_tokens": 3,
        "output_tokens": 5,
        "total_tokens": 8,
    }
    provider_body = json.loads(requests[0].content)
    assert provider_body["model"] == "gpt-4.1-mini"
    response_format = provider_body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    provider_schema = response_format["json_schema"]["schema"]
    intent_property = provider_schema["properties"]["intent"]
    assert intent_property["enum"] == ["consulta", "fuera_de_alcance"]
    assert "Elegi exactamente UNA" in intent_property["description"]
    assert provider_schema["properties"]["parameters"]["type"] == "array"
    assert provider_schema["properties"]["parameters"]["items"]["type"] == "object"
    assert provider_schema["properties"]["parameters"]["items"]["required"] == [
        "key",
        "value",
        "confidence",
    ]
    assert "_intents" not in provider_schema["properties"]
    assert provider_body["messages"][0]["role"] == "system"


def test_v5_interpretation_schema_translates_to_provider_compatible_union() -> None:
    contract_path = (
        Path(__file__).parents[4]
        / "contracts"
        / "agent"
        / "interpretation-schema.json"
    )
    schema = json.loads(contract_path.read_text(encoding="utf-8"))

    translated = _translate_schema(schema)
    act_items = translated["properties"]["acts"]["items"]

    assert len(act_items["anyOf"]) == 9
    assert _strict_compatible(translated) is True
    for branch in act_items["anyOf"]:
        assert branch["type"] == "object"
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == set(branch["properties"])
        assert "evidence_spans" not in branch["properties"]
        assert "evidence_text" in branch["properties"]

    serialized = json.dumps(translated)
    assert '"oneOf"' not in serialized
    assert '"allOf"' not in serialized
    assert '"if"' not in serialized
    assert '"then"' not in serialized


def test_preference_interpreter_schema_with_meta_keys_is_not_crashing() -> None:
    """The LLM preference interpreter catalogs resolve without 500ing.

    The interpreter passes the concept catalog and behavior rules as
    ``_catalog``/``_instructions`` schema siblings (its system-message
    contract). Every underscore-prefixed key is meta: it never reaches the
    provider JSON schema (which would force the model to echo it) and never
    crashes the translator the way ``_catalog`` used to.
    """
    payload = {
        "model": "gpt-4.1-mini",
        "model_version": "gpt-4.1-mini",
        "prompt_version": "agent-preference-interpret-v1",
        "schema_version": "preference-interpret-v1",
        "schema": {
            "resolution": "string",
            "reason": "string",
            "concept_key": "string",
            "polarity": "string",
            "value": "string",
            "confidence": "number",
            "matcher_type": "string",
            "params": [
                {"key": "string", "value": "string"}
            ],
            "_catalog": [
                {
                    "key": "balcon",
                    "description": "Balcon",
                    "matchers": ["categorical"],
                }
            ],
            "_instructions": "elige UNA resolucion: structured o unresolved",
        },
        "messages": [
            {
                "role": "system",
                "content": "Catalogo de conceptos disponibles...",
            },
            {"role": "user", "content": "quiero un depto luminoso"},
        ],
    }
    client, requests = _client()
    response = client.post("/v1/structured", json=payload)
    assert response.status_code == 200
    provider_schema = json.loads(requests[0].content)["response_format"]["json_schema"][
        "schema"
    ]
    assert "params" in provider_schema["properties"]
    assert "_catalog" not in provider_schema["properties"]
    assert "_instructions" not in provider_schema["properties"]
    roles = [item["role"] for item in json.loads(requests[0].content)["messages"]]
    assert roles[:2] == ["system", "system"]


def test_invalid_json_from_provider_is_corrected_once() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "no fue JSON valido" in body["messages"][-1]["content"]:
            content = json.dumps(_OK_CONTENT)
        else:
            content = "esto no es json"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 5,
                    "total_tokens": 8,
                },
            },
        )

    client, _ = _client(handler)
    response = client.post("/v1/structured", json=_INTENT_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["content"] == _OK_CONTENT


def test_invalid_json_after_correction_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "aun no es json"}}], "usage": {}},
        )

    client, _ = _client(handler)
    response = client.post("/v1/structured", json=_INTENT_PAYLOAD)
    assert response.status_code == 502


def test_provider_5xx_is_passed_through() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    client, _ = _client(handler)
    response = client.post("/v1/structured", json=_INTENT_PAYLOAD)
    assert response.status_code == 503


def test_shared_key_is_required_when_configured() -> None:
    client, _ = _client(shared_key="umbral-secret")
    response = client.post("/v1/structured", json=_INTENT_PAYLOAD)
    assert response.status_code == 401
    response = client.post(
        "/v1/structured",
        json=_INTENT_PAYLOAD,
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401
    response = client.post(
        "/v1/structured",
        json=_INTENT_PAYLOAD,
        headers={"Authorization": "Bearer umbral-secret"},
    )
    assert response.status_code == 200


def test_native_tool_calls_are_mapped_to_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "/responses" in request.url.path
        assert "tools" in body
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["tools"][0]["name"] == "find_matches"
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "fc_1",
                        "name": "find_matches",
                        "arguments": '{"page": 1, "limit": 5}',
                    }
                ],
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 5,
                    "total_tokens": 8,
                },
            },
        )

    client, _ = _client(handler)
    payload = dict(_INTENT_PAYLOAD)
    payload["tools"] = [
        {
            "name": "find_matches",
            "description": "Devuelve los recommendation items",
            "input_schema": {"page": "integer", "limit": "integer"},
        }
    ]
    response = client.post("/v1/structured", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == {
        "reply_text": "",
        "refs": [],
        "tool_calls": [{"tool": "find_matches", "args": {"page": 1, "limit": 5}}],
    }
    assert body["usage"]["total_tokens"] == 8


def test_native_tools_final_answer_is_json_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "/responses" in request.url.path
        if "no fue JSON valido" in str(body["input"][-1].get("content", "")):
            content = json.dumps({"reply_text": "ok", "refs": [], "tool_calls": []})
        else:
            content = "esto no es json"
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": content}],
                    }
                ],
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 5,
                    "total_tokens": 8,
                },
            },
        )

    client, _ = _client(handler)
    payload = dict(_INTENT_PAYLOAD)
    payload["tools"] = [
        {
            "name": "find_matches",
            "description": "Devuelve los recommendation items",
            "input_schema": {"page": "integer", "limit": "integer"},
        }
    ]
    response = client.post("/v1/structured", json=payload)
    assert response.status_code == 200
    assert response.json()["content"] == {
        "reply_text": "ok",
        "refs": [],
        "tool_calls": [],
    }


def test_translate_tool_schema_supports_enriched_v2_entries() -> None:
    from umbral.infrastructure.agent.model_gateway.server import _translate_tool_schema

    translated = _translate_tool_schema(
        {
            "decision": {
                "kind": "string",
                "enum": ["like", "dislike"],
                "description": "Reaccion del usuario",
            },
            "page": {"kind": "integer", "description": "Pagina"},
        }
    )
    assert translated["required"] == ["decision", "page"]
    assert translated["properties"]["decision"] == {
        "type": "string",
        "enum": ["like", "dislike"],
        "description": "Reaccion del usuario",
    }
    assert translated["properties"]["page"] == {
        "type": "integer",
        "description": "Pagina",
    }


def test_translate_tool_schema_supports_nullable_kinds() -> None:
    from umbral.infrastructure.agent.model_gateway.server import _translate_tool_schema

    translated = _translate_tool_schema(
        {"page": "integer", "run_id": "uuid|null", "change": "object"}
    )
    assert translated["required"] == ["page", "run_id", "change"]
    assert translated["properties"]["page"] == {"type": "integer"}
    assert translated["properties"]["run_id"] == {"type": ["string", "null"]}
    assert translated["properties"]["change"] == {"type": "object"}
    assert translated["additionalProperties"] is False


def test_native_history_messages_convert_to_responses_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "/responses" in request.url.path
        items = body["input"]
        assert items[0]["role"] == "user"
        assert items[1]["type"] == "function_call"
        assert items[1]["call_id"] == "umbral_call_0"
        assert items[1]["name"] == "find_matches"
        assert items[2]["type"] == "function_call_output"
        assert items[2]["call_id"] == "umbral_call_0"
        assert body["instructions"]
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 5,
                    "total_tokens": 8,
                },
            },
        )

    client, _ = _client(handler)
    payload = dict(_INTENT_PAYLOAD)
    payload["tools"] = [
        {
            "name": "find_matches",
            "description": "Devuelve los recommendation items",
            "input_schema": {"page": "integer", "limit": "integer"},
        }
    ]
    payload["messages"] = [
        {"role": "user", "content": "Quiero empezar a buscar"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "umbral_call_0",
                    "type": "function",
                    "function": {
                        "name": "find_matches",
                        "arguments": '{"page": 1, "limit": 5}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "umbral_call_0",
            "content": '{"tool": "find_matches", "status": "ok"}',
        },
    ]
    response = client.post("/v1/structured", json=payload)
    assert response.status_code == 200


def test_missing_openai_key_is_a_typed_500() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("provider must not be called without a key")

    transport = httpx.MockTransport(handler)
    app = create_app(
        openai_api_key="",
        http_client=httpx.Client(transport=transport),
    )
    response = TestClient(app).post("/v1/structured", json=_INTENT_PAYLOAD)
    assert response.status_code == 500


def test_translate_schema_reply_style_kind_notation() -> None:
    translated = _translate_schema(
        {
            "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
            "refs": {
                "kind": "list",
                "item": {"entity": "string", "id": "string"},
                "max_items": 10,
            },
            "tool_calls": {
                "kind": "list",
                "item": {"tool": "string", "args": "object"},
                "max_items": 5,
            },
        }
    )
    assert translated["required"] == ["reply_text", "refs", "tool_calls"]
    assert translated["additionalProperties"] is False
    reply_text = translated["properties"]["reply_text"]
    assert reply_text == {
        "type": "string",
        "minLength": 1,
        "maxLength": 2000,
    }
    assert translated["properties"]["refs"] == {
        "type": "array",
        "maxItems": 10,
        "items": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "id": {"type": "string"},
            },
            "required": ["entity", "id"],
            "additionalProperties": False,
        },
    }
    tool_calls = translated["properties"]["tool_calls"]
    assert tool_calls["type"] == "array"
    assert tool_calls["maxItems"] == 5
    assert tool_calls["items"]["properties"]["args"] == {"type": "object"}


def test_strict_compatibility_detects_free_form_objects() -> None:
    intent_schema = _translate_schema(
        {
            "intent": "string",
            "parameters": [],
            "high_impact_missing": [],
            "contradictions": [],
        }
    )
    assert _strict_compatible(intent_schema) is True
    reply_schema = _translate_schema(
        {
            "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
            "refs": {"kind": "list"},
            "tool_calls": {
                "kind": "list",
                "item": {"tool": "string", "args": "object"},
                "max_items": 5,
            },
        }
    )
    assert _strict_compatible(reply_schema) is False


def test_translate_schema_rejects_unknown_type() -> None:
    import pytest

    with pytest.raises(ValueError):
        _translate_schema({"field": "mystery"})
