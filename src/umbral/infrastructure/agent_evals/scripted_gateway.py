"""Deterministic scripted model gateway for agent evals (clarification Q4).

Serves the two call sites of the v3 graph — intent compilation and reply
generation — from a per-case script. The intent call returns the scripted
intent; each reply call consumes the next scripted reply; the final reply
builds its refs deterministically from the tool results message so the
grounded persist path accepts them (R-03/R-04).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from umbral.application.agent.contracts import ModelResult


class ScriptedModelGateway:
    """Deterministic per-case gateway; records every call."""

    def __init__(
        self,
        *,
        intent_response: Mapping[str, object],
        reply_sequence: Sequence[Mapping[str, object]],
        intent_prompt_version: str,
        reply_prompt_version: str,
        model_version: str = "provider-x-model-y",
        latency_ms: int = 1,
        input_tokens: int = 8,
        output_tokens: int = 16,
    ) -> None:
        self.intent_response = dict(intent_response)
        self.reply_sequence = [dict(item) for item in reply_sequence]
        self.intent_prompt_version = intent_prompt_version
        self.reply_prompt_version = reply_prompt_version
        self.model_version = model_version
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[Mapping[str, object]] = []
        self._reply_index = 0

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ModelResult:
        self.calls.append(
            {
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "model_version": model_version,
            }
        )
        if prompt_version == self.intent_prompt_version:
            content: Mapping[str, object] = self.intent_response
        else:
            content = self._next_reply(messages)
        return ModelResult(
            content=dict(content),
            model_version=self.model_version,
            status="success",
            latency_ms=self.latency_ms,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.input_tokens + self.output_tokens,
        )

    def _next_reply(
        self, messages: tuple[Mapping[str, object], ...]
    ) -> Mapping[str, object]:
        if not self.reply_sequence:
            return {"reply_text": "fuera de alcance", "refs": [], "tool_calls": []}
        reply = self.reply_sequence[
            min(self._reply_index, len(self.reply_sequence) - 1)
        ]
        self._reply_index += 1
        if reply.get("_final"):
            return build_final_reply(
                text=str(reply.get("text", "")),
                require_refs=bool(reply.get("require_refs", False)),
                messages=messages,
            )
        return reply


def build_final_reply(
    *,
    text: str,
    require_refs: bool,
    messages: tuple[Mapping[str, object], ...],
) -> Mapping[str, object]:
    """Build the final grounded reply of a case, deriving refs from the tool
    results message deterministically (only ids the persist path accepts)."""
    if not require_refs:
        return {"reply_text": text, "refs": [], "tool_calls": []}
    refs = _refs_from_tool_results(messages)
    return {"reply_text": text, "refs": refs, "tool_calls": []}


def _refs_from_tool_results(
    messages: tuple[Mapping[str, object], ...],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for message in messages:
        content: str | None = None
        if message.get("role") == "tool" and isinstance(message.get("content"), str):
            content = str(message["content"])
        elif message.get("role") == "user" and isinstance(
            message.get("content"), str
        ):
            if not str(message["content"]).startswith("Resultados de las tools"):
                continue
            _, separator, payload = str(message["content"]).partition("\n")
            if not separator:
                continue
            content = payload
        else:
            continue
        if content is None:
            continue
        for item in _parse_results(content):
            if not isinstance(item, Mapping):
                continue
            result = item.get("result")
            if not isinstance(result, Mapping):
                continue
            tool = item.get("tool")
            if tool == "find_matches":
                for raw in result.get("items", []):
                    if isinstance(raw, Mapping) and raw.get("listing_id"):
                        refs.append({"entity": "listing", "id": str(raw["listing_id"])})
            elif tool == "explain_match":
                listing_id = result.get("listing_id")
                if listing_id:
                    refs.append({"entity": "listing", "id": str(listing_id)})
                for raw in result.get("evidence_refs", []):
                    if isinstance(raw, Mapping) and raw.get("id"):
                        refs.append({"entity": "evidence_ref", "id": str(raw["id"])})
            elif tool == "compare_listings":
                for raw in result.get("cells", []):
                    if isinstance(raw, Mapping) and raw.get("listing_id"):
                        refs.append({"entity": "listing", "id": str(raw["listing_id"])})
    return refs


def _parse_results(content: str) -> list[object]:
    import json

    try:
        parsed = json.loads(content)
    except ValueError:
        return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return []
