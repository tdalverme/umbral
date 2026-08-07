"""Fake structured extraction adapter for local runs and conformance."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.criteria.contracts import ExtractionResult


class FakeStructuredExtractor:
    """Deterministic extractor: returns per-concept defaults or a failure."""

    def __init__(
        self, defaults: Mapping[str, Mapping[str, object]] | None = None
    ) -> None:
        self.defaults = dict(defaults or {})
        self.calls: list[Mapping[str, object]] = []

    def extract(
        self,
        *,
        concept_key: str,
        permitted_input: Mapping[str, object],
        schema: Mapping[str, object],
        version: str,
    ) -> ExtractionResult:
        self.calls.append(
            {
                "concept_key": concept_key,
                "permitted_input": dict(permitted_input),
                "version": version,
            }
        )
        default = self.defaults.get(concept_key)
        if default is None:
            return ExtractionResult(
                value=None,
                evidence_fragment=None,
                confidence=0.0,
                failed=True,
                failure_code="extraction.failed",
            )
        return ExtractionResult(
            value=dict(default),
            evidence_fragment=str(default.get("evidence", "evidencia fake")),
            confidence=_as_float(default.get("confidence", 0.9)),
        )


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.9
