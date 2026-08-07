"""Managed external provider adapter for structured extraction.

Only the permitted projection built by the extraction contract ever leaves the
system; 5xx/timeouts raise a transient marker (job-level retry), 4xx map to a
permanent ``failed`` observation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from umbral.application.criteria.contracts import ExtractionResult


class _TransientProviderError(Exception):
    """Marker mapped to a job-level transient failure by the service caller."""

    def __init__(self, concept_key: str) -> None:
        self.concept_key = concept_key
        super().__init__(f"provider transient failure: {concept_key}")


class ManagedStructuredExtractor:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        http_client: Any | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = http_client

    def extract(
        self,
        *,
        concept_key: str,
        permitted_input: Mapping[str, object],
        schema: Mapping[str, object],
        version: str,
    ) -> ExtractionResult:
        import httpx

        payload = {
            "model": self.model,
            "schema": dict(schema),
            "input": dict(permitted_input),
            "version": version,
        }
        try:
            response = self._request(payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if 500 <= error.response.status_code < 600:
                raise _TransientProviderError(concept_key) from error
            return ExtractionResult(
                value=None,
                evidence_fragment=None,
                confidence=0.0,
                failed=True,
                failure_code=f"provider.http_{error.response.status_code}",
            )
        except httpx.TimeoutException as error:
            raise _TransientProviderError(concept_key) from error
        except httpx.HTTPError:
            return ExtractionResult(
                value=None,
                evidence_fragment=None,
                confidence=0.0,
                failed=True,
                failure_code="provider.http_error",
            )
        body = response.json()
        return ExtractionResult(
            value=body.get("result"),
            evidence_fragment=(
                str(body["result"]["evidence"])
                if isinstance(body.get("result"), Mapping)
                else None
            ),
            confidence=0.0,
        )

    def _request(self, payload: Mapping[str, object]) -> Any:
        import httpx

        client = self._client
        if client is None:
            client = httpx.Client(timeout=self.timeout_seconds)
        return client.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=dict(payload),
        )
