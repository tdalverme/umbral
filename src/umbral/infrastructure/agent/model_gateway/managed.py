"""HTTP structured-output model gateway with bounded retry and usage (UM-H4-004)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from umbral.application.agent.contracts import ModelResult

_Schema = Mapping[str, object]
_STATUS_TIMEOUT = "timeout"
_STATUS_TRANSIENT = "transient"
_STATUS_HTTP_ERROR = "http_error"
_STATUS_SUCCESS = "success"


class ManagedModelGateway:
    """Provider-agnostic structured output via a single JSON endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 0.1,
        http_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self._client = http_client
        self.sleep = sleep

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: _Schema,
        schema_version: str,
        prompt_version: str,
        model_version: str,
    ) -> ModelResult:
        payload = {
            "model": self.model,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "schema": dict(schema),
            "messages": [dict(item) for item in messages],
        }
        for attempt in range(self.max_retries + 1):
            status, body, latency_ms = self._request(payload)
            if status == _STATUS_TIMEOUT:
                if attempt < self.max_retries:
                    self.sleep(self.backoff_base_seconds * (2**attempt))
                    continue
                return ModelResult(
                    content=None,
                    model_version=model_version,
                    status="timeout",
                    latency_ms=latency_ms,
                    error_code="agent.timeout",
                )
            if status == _STATUS_TRANSIENT:
                if attempt < self.max_retries:
                    self.sleep(self.backoff_base_seconds * (2**attempt))
                    continue
                return ModelResult(
                    content=None,
                    model_version=model_version,
                    status="error",
                    latency_ms=latency_ms,
                    error_code=f"provider.http_{_status_code(body)}",
                )
            if status == _STATUS_HTTP_ERROR:
                return ModelResult(
                    content=None,
                    model_version=model_version,
                    status="error",
                    latency_ms=latency_ms,
                    error_code="provider.http_error",
                )
            content = _validated_content(body)
            if content is not None:
                raw_usage = body.get("usage", {})
                usage = raw_usage if isinstance(raw_usage, Mapping) else {}
                return ModelResult(
                    content=content,
                    model_version=model_version,
                    status="success",
                    latency_ms=latency_ms,
                    input_tokens=_as_int(usage.get("input_tokens"), 0),
                    output_tokens=_as_int(usage.get("output_tokens"), 0),
                    total_tokens=_as_int(usage.get("total_tokens"), 0),
                )
            if attempt < self.max_retries:
                self.sleep(self.backoff_base_seconds * (2**attempt))
                continue
            return ModelResult(
                content=None,
                model_version=model_version,
                status="invalid_output",
                latency_ms=latency_ms,
                error_code="agent.invalid_output",
            )
        return ModelResult(
            content=None,
            model_version=model_version,
            status="error",
            latency_ms=0,
            error_code="agent.error",
        )

    def _request(
        self, payload: Mapping[str, object]
    ) -> tuple[str, Mapping[str, object], int]:
        import httpx

        started = time.perf_counter()
        client = self._client
        if client is None:
            client = httpx.Client(timeout=self.timeout_seconds)
        try:
            response = client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=dict(payload),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            if 500 <= code < 600:
                return _STATUS_TRANSIENT, {"code": code}, _elapsed_ms(started)
            return _STATUS_HTTP_ERROR, {"code": code}, _elapsed_ms(started)
        except httpx.TimeoutException:
            return _STATUS_TIMEOUT, {}, _elapsed_ms(started)
        except httpx.HTTPError:
            return _STATUS_HTTP_ERROR, {}, _elapsed_ms(started)
        try:
            body = response.json()
        except ValueError:
            return _STATUS_HTTP_ERROR, {}, _elapsed_ms(started)
        if not isinstance(body, Mapping):
            return _STATUS_HTTP_ERROR, {}, _elapsed_ms(started)
        return _STATUS_SUCCESS, body, _elapsed_ms(started)


def _validated_content(body: Mapping[str, object]) -> Mapping[str, object] | None:
    content = body.get("content")
    if not isinstance(content, Mapping):
        return None
    text = content.get("reply_text")
    refs = content.get("refs")
    if not isinstance(text, str) or not (1 <= len(text) <= 2000):
        return None
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if not isinstance(ref, Mapping):
            return None
        if not isinstance(ref.get("entity"), str) or not isinstance(ref.get("id"), str):
            return None
    return dict(content)


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _status_code(body: Mapping[str, object]) -> int:
    code = body.get("code")
    return code if isinstance(code, int) else 0


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
