"""Deterministic model gateway for tests and local default (H4.1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from umbral.application.agent.contracts import ModelResult

_DEFAULT_REPLY: Mapping[str, object] = {
    "reply_text": "Respuesta de prueba de Umbral sin datos suficientes.",
    "refs": [],
}


class FakeModelGateway:
    """Returns a deterministic structured reply and records every call."""

    def __init__(
        self,
        *,
        model_version: str = "local-fake",
        latency_ms: int = 1,
        input_tokens: int = 8,
        output_tokens: int = 16,
        raise_on_call: int | None = None,
        replies: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self.model_version = model_version
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.raise_on_call = raise_on_call
        self.replies = dict(replies or {})
        self.calls: list[Mapping[str, object]] = []

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
                "messages": messages,
                "schema_version": schema_version,
                "prompt_version": prompt_version,
                "model_version": model_version,
            }
        )
        if self.raise_on_call is not None and len(self.calls) == self.raise_on_call:
            raise RuntimeError("fake model provider crash")
        reply = self.replies.get(prompt_version, _DEFAULT_REPLY)
        return ModelResult(
            content=dict(reply),
            model_version=self.model_version,
            status="success",
            latency_ms=self.latency_ms,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.input_tokens + self.output_tokens,
        )
