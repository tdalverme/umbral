"""US4: managed provider adapter behavior with a mocked HTTP client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from umbral.application.criteria.contracts import ExtractionResult
from umbral.infrastructure.criteria.extractors.managed import (
    ManagedStructuredExtractor,
)


class _Response:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.url = "https://provider.example.invalid/extract"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                "error",
                request=cast(Any, None),
                response=cast(Any, SimpleNamespace(status_code=self.status_code)),
            )

    def json(self) -> object:
        return self._payload


class _Client:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.sent: list[dict[str, Any]] = []

    def post(
        self, endpoint: str, *, headers: object, json: dict[str, object]
    ) -> object:
        self.sent.append({"endpoint": endpoint, "headers": headers, "json": json})
        return self.responses.pop(0)


def _extractor(client: _Client) -> ManagedStructuredExtractor:
    return ManagedStructuredExtractor(
        endpoint="https://provider.example.invalid/extract",
        api_key="secret-key",
        model="model-x",
        http_client=client,
    )


def test_managed_extractor_sends_only_schema_and_permitted_input() -> None:
    client = _Client(
        [
            _Response(
                200, {"result": {"value": "media", "evidence": "x", "confidence": 0.8}}
            )
        ]
    )
    result: ExtractionResult = _extractor(client).extract(
        concept_key="luminosidad",
        permitted_input={"description_text": "luminoso"},
        schema={"type": "object"},
        version="v1",
    )
    assert result.value == {"value": "media", "evidence": "x", "confidence": 0.8}
    sent = client.sent[0]
    assert sent["json"]["model"] == "model-x"
    assert sent["json"]["input"] == {"description_text": "luminoso"}
    assert "secret-key" in str(sent["headers"])


def test_managed_extractor_4xx_is_a_permanent_failure() -> None:
    client = _Client([_Response(400)])
    result = _extractor(client).extract(
        concept_key="luminosidad",
        permitted_input={},
        schema={},
        version="v1",
    )
    assert result.failed is True
    assert result.failure_code == "provider.http_400"


def test_managed_extractor_5xx_is_a_transient_failure() -> None:
    client = _Client([_Response(503)])
    try:
        _extractor(client).extract(
            concept_key="luminosidad",
            permitted_input={},
            schema={},
            version="v1",
        )
    except Exception as error:  # noqa: BLE001
        assert "provider transient" in str(error).lower()
    else:
        raise AssertionError("expected transient provider failure")
