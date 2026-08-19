# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Preference interpreter (LLM -> structured/unresolved) unit tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.preference_interpreter import (
    ConceptOption,
    resolve_concept,
)

_CATALOG = (
    ConceptOption(
        key="luminosidad",
        description="Luminosidad",
        matchers=("semantic_feature",),
    ),
    ConceptOption(
        key="proximidad_cafes",
        description="Proximidad a cafes",
        matchers=("signal_score",),
    ),
)


class _Gateway:
    def __init__(self, content: Mapping[str, object] | None) -> None:
        self.received_schema: dict[str, object] = {}
        self.received_messages: tuple[Mapping[str, object], ...] = ()
        self._content = content

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
        del schema_version, prompt_version, model_version, tools
        self.received_schema = dict(schema)
        self.received_messages = messages
        content = (
            dict(self._content)
            if isinstance(self._content, Mapping)
            else None
        )
        if content is None:
            return ModelResult(
                content=None,
                model_version="fake",
                status="error",
                latency_ms=0,
                error_code="agent.error",
            )
        return ModelResult(
            content=content,
            model_version="fake",
            status="success",
            latency_ms=1,
        )


def _resolve(content: Mapping[str, object] | None):
    return resolve_concept(
        phrase="quisiera un depto colorido",
        concepts=_CATALOG,
        gateway=_Gateway(content),
        prompt_version="agent-preference-interpret-v1",
        model_version="fake",
    )


def test_gateway_failure_returns_none() -> None:
    interpretation = _resolve(None)
    assert interpretation is None


def test_resolution_structured_maps_concept() -> None:
    interpretation = _resolve(
        {
            "resolution": "structured",
            "concept_key": "luminosidad",
            "polarity": "positive",
            "value": None,
            "confidence": 0.9,
            "matcher_type": "semantic_feature",
            "params": [{"key": "concept", "value": "luminosidad"}],
        }
    )
    assert interpretation is not None
    assert interpretation.kind == "structured"
    assert interpretation.concept_key == "luminosidad"
    assert interpretation.polarity == "positive"
    assert interpretation.matcher_type == "semantic_feature"
    assert interpretation.confidence == 0.9


def test_resolution_unresolved_keeps_reason() -> None:
    interpretation = _resolve(
        {"resolution": "unresolved", "reason": "sin concepto en catalogo"}
    )
    assert interpretation is not None
    assert interpretation.kind == "unresolved"
    assert "sin concepto" in interpretation.reason


def test_non_published_concept_becomes_unresolved() -> None:
    interpretation = _resolve(
        {
            "resolution": "structured",
            "concept_key": "parque",
            "polarity": "positive",
            "confidence": 0.8,
            "matcher_type": "signal_score",
        }
    )
    assert interpretation is not None
    assert interpretation.kind == "unresolved"


def test_invalid_matcher_becomes_unresolved() -> None:
    interpretation = _resolve(
        {
            "resolution": "structured",
            "concept_key": "luminosidad",
            "polarity": "positive",
            "confidence": 0.8,
            "matcher_type": "categorical",
        }
    )
    assert interpretation is not None
    assert interpretation.kind == "unresolved"


def test_schema_is_output_only_and_catalog_rides_the_system_message() -> None:
    gateway = _Gateway({"resolution": "unresolved", "reason": "test"})
    resolve_concept(
        phrase="x",
        concepts=_CATALOG,
        gateway=gateway,
        prompt_version="v1",
        model_version="m",
    )
    assert "_catalog" not in gateway.received_schema
    assert "_instructions" not in gateway.received_schema
    assert set(gateway.received_schema) >= {
        "resolution",
        "reason",
        "concept_key",
        "polarity",
        "value",
        "confidence",
        "matcher_type",
        "params",
    }
    system = next(
        item.get("content", "")
        for item in gateway.received_messages
        if item.get("role") == "system"
    )
    assert "luminosidad: Luminosidad" in system
    assert "proximidad_cafes: Proximidad a cafes" in system
    assert "matcher_type (uno de los matchers validos" in system
    assert [item.get("role") for item in gateway.received_messages] == [
        "system",
        "user",
    ]
