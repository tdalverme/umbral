"""Standalone managed model endpoint for the agent gateway (ADR 0001).

Serves the ``ManagedModelGateway`` contract: receives ``{model, messages,
schema}`` and answers ``{content, usage}`` by calling an OpenAI-compatible
provider with structured JSON output. It is a separate service from the
product API: run with ``uvicorn umbral.infrastructure.agent.model_gateway.
server:app`` and point ``AGENT_MANAGED_ENDPOINT`` at it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, Literal

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_JSON_MODE_PROMPT = (
    "Eres el agente del radar de vivienda Umbral. Responde unicamente con el "
    "objeto JSON definido por el esquema de la solicitud, sin texto adicional."
)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    input_schema: dict[str, Any] = Field(default_factory=dict)


class StructuredRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=200)
    schema_version: str = Field(min_length=1, max_length=200)
    output_schema: dict[str, Any] = Field(validation_alias="schema")
    tools: list[ToolSpec] | None = None
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)


class StructuredResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: dict[str, Any]
    usage: dict[str, int]


def _translate_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Translate the simplified schema notation into a strict JSON Schema.

    The simplified notation is the published contract style: field values are
    either type strings (``"string"``, ``"number"``), ``{"kind": ...}``
    descriptors (reply style) or plain array-of-objects (intent style). The
    optional ``_intents`` sibling carries the allowed intent names.

    Topology-v4 passes JSON-Schema-style documents (``"$defs"`` plus
    ``"$ref"``, e.g. the interpretation contract); those are translated
    meta-aware instead.
    """
    if not isinstance(schema, dict):
        raise ValueError(f"unsupported schema node: {type(schema).__name__}")
    if "$defs" in schema and isinstance(schema["$defs"], dict):
        return _translate_json_schema(schema, defs=schema["$defs"])

    def translate_value(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            type_map = {
                "string": "string",
                "number": "number",
                "boolean": "boolean",
                "object": "object",
            }
            kind = type_map.get(value)
            if kind is None:
                raise ValueError(f"unknown simplified type: {value}")
            return {"type": kind}
        if isinstance(value, list):
            if not value:
                return {"type": "array"}
            return {"type": "array", "items": translate_value(value[0])}
        if not isinstance(value, dict):
            raise ValueError(f"unsupported schema node: {type(value).__name__}")
        if "enum" in value and "properties" not in value:
            if not isinstance(value["enum"], list) or not all(
                isinstance(item, str) for item in value["enum"]
            ):
                raise ValueError("enum must be a list of strings")
            result: dict[str, Any] = {"type": "string", "enum": list(value["enum"])}
            if isinstance(value.get("description"), str):
                result["description"] = value["description"]
            return result
        kind = value.get("kind")
        if kind == "list":
            result = {"type": "array"}
            if isinstance(value.get("item"), (dict, str)):
                result["items"] = translate_value(value["item"])
            if isinstance(value.get("max_items"), int):
                result["maxItems"] = value["max_items"]
            if isinstance(value.get("description"), str):
                result["description"] = value["description"]
            return result
        if kind == "nullable_string":
            result = {"type": ["string", "null"]}
            if isinstance(value.get("min_length"), int):
                result["minLength"] = value["min_length"]
            if isinstance(value.get("max_length"), int):
                result["maxLength"] = value["max_length"]
            if isinstance(value.get("description"), str):
                result["description"] = value["description"]
            return result
        if kind in {"string", "number", "boolean"}:
            result = {"type": kind}
            if kind == "string":
                if isinstance(value.get("min_length"), int):
                    result["minLength"] = value["min_length"]
                if isinstance(value.get("max_length"), int):
                    result["maxLength"] = value["max_length"]
            if isinstance(value.get("description"), str):
                result["description"] = value["description"]
            if isinstance(value.get("enum"), list) and all(
                isinstance(item, str) for item in value["enum"]
            ):
                result["enum"] = list(value["enum"])
            return result
        return _translate_object(value)

    def _translate_object(obj: dict[str, Any]) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for key, item in obj.items():
            if key.startswith("_"):
                continue
            properties[key] = translate_value(item)
            required.append(key)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    result = _translate_object(schema)
    intents = schema.get("_intents")
    if isinstance(intents, list) and intents:
        names: list[str] = []
        lines: list[str] = []
        for item in intents:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            names.append(item["name"])
            line = item["name"]
            if isinstance(item.get("description"), str) and item["description"]:
                line += f": {item['description']}"
            examples = item.get("examples")
            if isinstance(examples, list):
                sample = [
                    str(example)
                    for example in examples
                    if isinstance(example, str) and example
                ]
                if sample:
                    line += " (ej: " + "; ".join(sample[:3]) + ")"
            lines.append(line)
        if names:
            result["properties"]["intent"] = {
                "type": "string",
                "enum": names,
                "description": "Elegi exactamente UNA de estas opciones:\n"
                + "\n".join(lines),
            }
    return result


def _translate_json_schema(
    node: dict[str, Any], defs: Mapping[str, Any]
) -> dict[str, Any]:
    """Translate a JSON-Schema-style document into a strict JSON Schema.

    Handles the subset used by the conversation contracts: object and array
    shapes, ``$ref`` into ``$defs``, discriminated ``oneOf`` unions, shared
    ``allOf`` properties, enums, consts and scalar bounds. OpenAI Structured
    Outputs supports ``anyOf`` but not the source contract's ``oneOf``/``allOf``
    composition, so unions are compiled into provider-compatible schemas and
    the full source contract remains the local validation authority.
    """
    node = _resolve_ref(node, defs)
    conditional_variants = _conditional_property_variants(node, defs)
    node = _merge_all_of(node, defs)
    one_of = node.get("oneOf")
    if isinstance(one_of, list):
        variants: list[dict[str, Any]] = []
        for branch in one_of:
            if not isinstance(branch, dict):
                raise ValueError("oneOf entries must be objects")
            variants.append(_translate_json_schema(branch, defs))
        return {"anyOf": variants}

    schema_type = node.get("type")
    result: dict[str, Any] = {}
    if isinstance(schema_type, list):  # union like ["string", "null"]
        result["type"] = [str(item) for item in schema_type]
    elif isinstance(schema_type, str):
        result["type"] = schema_type
    if isinstance(node.get("description"), str):
        result["description"] = node["description"]
    if isinstance(node.get("enum"), list):
        result["enum"] = list(node["enum"])
    if "const" in node:
        result["enum"] = [node["const"]]
    if "type" not in result:
        inferred_type = _infer_enum_type(result.get("enum"))
        if inferred_type is not None:
            result["type"] = inferred_type
    if "minLength" in node:
        result["minLength"] = node["minLength"]
    if "maxLength" in node:
        result["maxLength"] = node["maxLength"]
    for key in ("minimum", "maximum", "minItems", "maxItems"):
        if key in node:
            result[key] = node[key]
    if "items" in node:
        result["items"] = _translate_json_schema(node["items"], defs)
    if isinstance(node.get("properties"), dict):
        properties: dict[str, Any] = {}
        declared_required = {
            item for item in node.get("required", []) if isinstance(item, str)
        }
        for key, raw in node["properties"].items():
            if raw == {} and key in conditional_variants:
                properties[key] = {
                    "anyOf": [
                        _translate_json_schema(variant, defs)
                        for variant in conditional_variants[key]
                    ]
                }
            else:
                properties[key] = _translate_json_schema(raw, defs)
            if key not in declared_required:
                properties[key] = _nullable_schema(properties[key])
        result["properties"] = properties
        result["required"] = list(properties)
        result["additionalProperties"] = False
    return result


def _resolve_ref(node: dict[str, Any], defs: Mapping[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return node
    name = ref.removeprefix("#/$defs/")
    if not isinstance(defs, Mapping) or name not in defs:
        raise ValueError(f"unresolved schema $ref: {ref}")
    resolved = defs[name]
    if not isinstance(resolved, dict):
        raise ValueError(f"invalid $defs entry: {name}")
    return resolved


def _merge_all_of(node: dict[str, Any], defs: Mapping[str, Any]) -> dict[str, Any]:
    """Inline non-conditional ``allOf`` object members into ``node``."""

    merged = {key: value for key, value in node.items() if key != "allOf"}
    own_properties = node.get("properties")
    if isinstance(own_properties, dict):
        merged["properties"] = dict(own_properties)
    required = [item for item in node.get("required", []) if isinstance(item, str)]

    clauses = node.get("allOf")
    if not isinstance(clauses, list):
        if required:
            merged["required"] = required
        return merged

    for clause in clauses:
        if not isinstance(clause, dict) or any(
            key in clause for key in ("if", "then", "else")
        ):
            continue
        branch = _merge_all_of(_resolve_ref(clause, defs), defs)
        branch_properties = branch.get("properties")
        if isinstance(branch_properties, dict):
            properties = merged.setdefault("properties", {})
            if isinstance(properties, dict):
                for key, value in branch_properties.items():
                    properties.setdefault(key, value)
        for item in branch.get("required", []):
            if isinstance(item, str) and item not in required:
                required.append(item)
        for key, value in branch.items():
            if key not in {"properties", "required"}:
                merged.setdefault(key, value)
    if required:
        merged["required"] = required
    return merged


def _conditional_property_variants(
    node: dict[str, Any], defs: Mapping[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Collect property types from conditional branches for provider output."""

    variants: dict[str, list[dict[str, Any]]] = {}
    clauses = node.get("allOf")
    if not isinstance(clauses, list):
        return variants
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        then = clause.get("then")
        if not isinstance(then, dict):
            continue
        properties = then.get("properties")
        if not isinstance(properties, dict):
            continue
        for key, value in properties.items():
            if isinstance(value, dict):
                variants.setdefault(key, []).append(value)
    return variants


def _infer_enum_type(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    types = {type(item) for item in value}
    if types == {str}:
        return "string"
    if types == {bool}:
        return "boolean"
    if types == {int}:
        return "integer"
    if types <= {int, float}:
        return "number"
    if types == {type(None)}:
        return "null"
    return None


def _nullable_schema(node: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [node, {"type": "null"}]}


def _strict_compatible(node: object) -> bool:
    """True when the translated schema can run under OpenAI strict mode.

    Strict mode rejects free-form objects (an object without declared
    properties, e.g. tool call ``args``), requires ``items`` on arrays and
    rejects union types (nullable fields).
    """
    if not isinstance(node, dict):
        return True
    node_type = node.get("type")
    if isinstance(node_type, list):
        return False
    if node_type == "object" and "properties" not in node:
        return False
    return all(_strict_compatible(value) for value in node.values())


_TOOL_KINDS = {
    "integer": "integer",
    "string": "string",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
    "uuid": "string",
    "datetime": "string",
}


def _translate_tool_schema(input_schema: dict[str, Any]) -> dict[str, Any]:
    """Translate the tool contract's input schema notation to JSON Schema.

    Supports both the plain form (``{field: "kind"}``) and the enriched v2
    form (``{field: {"kind", "description", "enum"}}``).
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field, raw in input_schema.items():
        if isinstance(raw, dict):
            kind = str(raw.get("kind", ""))
            description = raw.get("description")
            enum = raw.get("enum")
        else:
            kind = str(raw)
            description = None
            enum = None
        nullable = kind.endswith("|null")
        base = kind[:-5] if nullable else kind
        json_type = _TOOL_KINDS.get(base)
        if json_type is None:
            raise ValueError(f"unknown tool arg kind: {kind}")
        node: dict[str, Any] = (
            {"type": [json_type, "null"]} if nullable else {"type": json_type}
        )
        if isinstance(description, str) and description:
            node["description"] = description
        if isinstance(enum, list) and enum and all(
            isinstance(item, str) for item in enum
        ):
            node["enum"] = list(enum)
        properties[field] = node
        required.append(field)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _native_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for tool in tools:
        try:
            parameters = _translate_tool_schema(tool.input_schema)
        except ValueError as error:
            raise HTTPException(
                status_code=500, detail=f"invalid tool schema: {error}"
            ) from error
        definitions.append(
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters,
            }
        )
    return definitions


def _native_calls_to_content(
    native_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    for call in native_calls:
        function = call.get("function")
        if isinstance(function, Mapping):
            name = function.get("name")
            raw_args = function.get("arguments")
        else:
            name = call.get("name")
            raw_args = call.get("arguments")
        if not isinstance(name, str):
            continue
        args: object = {}
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except ValueError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append({"tool": name, "args": args})
    return {"reply_text": "", "refs": [], "tool_calls": calls}


def create_app(
    *,
    openai_api_key: str | None = None,
    shared_key: str | None = None,
    provider_url: str = _OPENAI_CHAT_URL,
    responses_url: str = _OPENAI_RESPONSES_URL,
    timeout_seconds: float = 30.0,
    http_client: httpx.Client | None = None,
) -> FastAPI:
    """Build the gateway app; configuration defaults come from the environment."""

    api_key = openai_api_key if openai_api_key is not None else os.getenv(
        "MODEL_GATEWAY_OPENAI_API_KEY", ""
    )
    expected_shared_key = shared_key if shared_key is not None else os.getenv(
        "MODEL_GATEWAY_SHARED_KEY", ""
    )
    client = http_client
    if client is None:
        client = httpx.Client(timeout=timeout_seconds)

    app = FastAPI(title="Umbral managed model gateway")

    def _authorize(authorization: str | None) -> None:
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="gateway misconfigured: MODEL_GATEWAY_OPENAI_API_KEY missing",
            )
        if not expected_shared_key:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        if authorization.removeprefix("Bearer ").strip() != expected_shared_key:
            raise HTTPException(status_code=401, detail="invalid bearer token")

    def _call_provider(
        messages: list[dict[str, str]],
        model: str,
        json_schema: dict[str, Any],
        strict: bool,
        tools: list[dict[str, Any]] | None = None,
    ) -> httpx.Response:
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        else:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "umbral_structured_output",
                    "schema": json_schema,
                    "strict": strict,
                },
            }
        try:
            response = client.post(
                provider_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request,
            )
        except httpx.TimeoutException as error:
            raise HTTPException(status_code=504, detail="provider timeout") from error
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502, detail="provider unreachable"
            ) from error
        return response

    def _structured_call(
        messages: list[dict[str, str]],
        model: str,
        json_schema: dict[str, Any],
        strict: bool,
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[Any, dict[str, int]]:
        response = _call_provider(messages, model, json_schema, strict, tools)
        if response.status_code >= 500:
            raise HTTPException(
                status_code=response.status_code, detail="provider error"
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="provider rejected request",
            )
        body = response.json()
        message = body.get("choices", [{}])[0].get("message", {})
        usage_raw = body.get("usage") or {}
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens", 0),
            "output_tokens": usage_raw.get("completion_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
        }
        native_calls = (
            message.get("tool_calls") if isinstance(message, Mapping) else None
        )
        if isinstance(native_calls, list) and native_calls:
            return _native_calls_to_content(native_calls), usage
        content = message.get("content", "")
        return content, usage

    def _responses_input(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Split chat-style messages into Responses API instructions + input.

        Assistant tool-call messages become ``function_call`` items and tool
        results become ``function_call_output`` items (Responses API shape).
        """
        instructions: list[str] = []
        input_items: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", ""))
            if role == "system":
                instructions.append(str(message.get("content", "")))
                continue
            if role == "assistant" and message.get("tool_calls"):
                for call in message["tool_calls"]:
                    if not isinstance(call, Mapping):
                        continue
                    function = call.get("function")
                    if not isinstance(function, Mapping):
                        continue
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": str(call.get("id", "")),
                            "name": str(function.get("name", "")),
                            "arguments": str(function.get("arguments", "{}")),
                        }
                    )
                continue
            if role == "tool":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(message.get("tool_call_id", "")),
                        "output": str(message.get("content", "")),
                    }
                )
                continue
            input_items.append(
                {"role": role, "content": str(message.get("content", ""))}
            )
        return "\n\n".join(instructions), input_items

    def _responses_call(
        messages: list[dict[str, str]],
        model: str,
        json_schema: dict[str, Any],
        strict: bool,
        tools: list[dict[str, Any]],
    ) -> tuple[Any, dict[str, int]]:
        instructions, input_items = _responses_input(messages)
        request: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "umbral_structured_output",
                    "schema": json_schema,
                    "strict": strict,
                }
            },
        }
        try:
            response = client.post(
                responses_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request,
            )
        except httpx.TimeoutException as error:
            raise HTTPException(status_code=504, detail="provider timeout") from error
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502, detail="provider unreachable"
            ) from error
        if response.status_code >= 500:
            raise HTTPException(
                status_code=response.status_code, detail="provider error"
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="provider rejected request",
            )
        body = response.json()
        usage_raw = body.get("usage") or {}
        usage = {
            "input_tokens": usage_raw.get("input_tokens", 0),
            "output_tokens": usage_raw.get("output_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
        }
        native_calls: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for raw_item in body.get("output", []) or []:
            if not isinstance(raw_item, Mapping):
                continue
            item = dict(raw_item)
            item_type = item.get("type")
            if item_type == "function_call":
                native_calls.append(item)
            elif item_type == "message":
                for part in item.get("content") or []:
                    if isinstance(part, Mapping) and part.get("type") == "output_text":
                        text_parts.append(str(part.get("text", "")))
        if native_calls:
            return _native_calls_to_content(native_calls), usage
        return "".join(text_parts), usage

    @app.post(
        "/v1/structured",
        response_model=StructuredResponse,
        operation_id="generateStructured",
    )
    def generate_structured(
        payload: StructuredRequest,
        authorization: str | None = Header(default=None),
    ) -> StructuredResponse:
        _authorize(authorization)
        try:
            json_schema = _translate_schema(payload.output_schema)
        except ValueError as error:
            raise HTTPException(
                status_code=500, detail=f"invalid schema payload: {error}"
            ) from error
        strict = _strict_compatible(json_schema)
        native_tools = _native_tools(payload.tools) if payload.tools else None
        if native_tools:
            system_prompt = (
                _JSON_MODE_PROMPT
                + " Podes llamar las tools disponibles cuando necesites datos; "
                "al responder, usa unicamente el objeto JSON del esquema."
            )
        else:
            system_prompt = _JSON_MODE_PROMPT
        messages = [
            {"role": "system", "content": system_prompt},
            *(
                {key: value for key, value in dict(item).items() if value is not None}
                for item in payload.messages
            ),
        ]
        for attempt in (0, 1):
            if native_tools:
                raw, usage = _responses_call(
                    messages, payload.model, json_schema, strict, native_tools
                )
            else:
                raw, usage = _structured_call(
                    messages, payload.model, json_schema, strict, None
                )
            if isinstance(raw, str):
                try:
                    content = json.loads(raw)
                except (TypeError, ValueError):
                    if attempt == 0:
                        messages.append({"role": "assistant", "content": raw})
                        messages.append(
                            {
                                "role": "user",
                                "content": "Tu respuesta anterior no fue JSON valido. "
                                "Responde unicamente el JSON, sin texto adicional.",
                            }
                        )
                        continue
                    raise HTTPException(
                        status_code=502, detail="provider returned invalid JSON"
                    )
            else:
                content = raw
            if not isinstance(content, dict):
                raise HTTPException(
                    status_code=502, detail="provider returned invalid JSON"
                )
            return StructuredResponse(content=content, usage=usage)
        raise HTTPException(status_code=502, detail="provider returned invalid JSON")

    return app


app = create_app()
