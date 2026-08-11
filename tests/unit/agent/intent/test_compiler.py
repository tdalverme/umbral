"""Intent compiler unit tests (UM-H4-017, T015)."""

from __future__ import annotations

from typing import Mapping

import pytest

from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.intent.contracts import (
    IntentCompilationFailed,
    IntentUnclassified,
)
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

_PROMPT = "agent-intent-v1"


def _compiler(
    *,
    replies: Mapping[str, Mapping[str, object]],
    gateway: FakeModelGateway | None = None,
) -> IntentCompiler:
    fake = gateway or FakeModelGateway(replies=replies)
    return IntentCompiler(
        gateway=fake,
        contract=load_intent_contract(),
        prompt_version=_PROMPT,
        model_version="local-fake",
    )


def test_compile_classifies_refinamiento_with_parameters() -> None:
    compiler = _compiler(
        replies={
            _PROMPT: {
                "intent": "refinamiento",
                "parameters": [
                    {"key": "budget", "value": "900", "confidence": 0.95}
                ],
                "high_impact_missing": [],
                "contradictions": [],
            }
        }
    )
    compilation = compiler.compile(message_text="subí el presupuesto a 900")
    assert compilation.intent == "refinamiento"
    assert compilation.parameters[0].key == "budget"
    assert compilation.parameters[0].value == "900"
    assert compilation.parameters[0].confidence == 0.95
    assert compilation.allowed_tools == ("propose_search_profile_update",)


def test_compile_out_of_scope_allows_no_tools() -> None:
    compiler = _compiler(
        replies={
            _PROMPT: {
                "intent": "fuera_de_alcance",
                "parameters": [],
                "high_impact_missing": [],
                "contradictions": [],
            }
        }
    )
    compilation = compiler.compile(
        message_text="quiero crear un radar nuevo desde cero"
    )
    assert compilation.intent == "fuera_de_alcance"
    assert compilation.allowed_tools == ()


def test_compile_consulta_maps_to_read_tools() -> None:
    compiler = _compiler(
        replies={
            _PROMPT: {
                "intent": "consulta",
                "parameters": [],
                "high_impact_missing": [],
                "contradictions": [],
            }
        }
    )
    compilation = compiler.compile(message_text="qué criterios tengo?")
    assert "find_matches" in compilation.allowed_tools
    assert "apply_search_profile_update" not in compilation.allowed_tools


def test_compile_reports_missing_and_contradictions() -> None:
    compiler = _compiler(
        replies={
            _PROMPT: {
                "intent": "refinamiento",
                "parameters": [
                    {"key": "budget", "value": "700", "confidence": 0.5}
                ],
                "high_impact_missing": ["zona"],
                "contradictions": [
                    {"key": "budget", "current_value": "900", "requested": "700"}
                ],
            }
        }
    )
    compilation = compiler.compile(message_text="quiero algo más barato")
    assert compilation.high_impact_missing == ("zona",)
    assert compilation.contradictions[0].key == "budget"


def test_compile_unclassified_intent_is_rejected() -> None:
    compiler = _compiler(
        replies={_PROMPT: {"intent": "inventada", "parameters": []}}
    )
    with pytest.raises(IntentUnclassified):
        compiler.compile(message_text="hola")


def test_compile_passes_prompt_schema_with_intent_enum() -> None:
    from umbral.application.agent.contracts import ModelResult

    class RecordingGateway:
        def __init__(self) -> None:
            self.schema: Mapping[str, object] = {}

        def generate_structured(self, **kwargs: object) -> ModelResult:
            self.schema = kwargs.get("schema", {})  # type: ignore[assignment]
            return ModelResult(
                content={
                    "intent": "consulta",
                    "parameters": [],
                    "high_impact_missing": [],
                    "contradictions": [],
                },
                model_version="local-fake",
                status="success",
                latency_ms=1,
                input_tokens=8,
                output_tokens=16,
                total_tokens=24,
            )

    gateway = RecordingGateway()
    compiler = _compiler(replies={}, gateway=gateway)  # type: ignore[arg-type]
    compiler.compile(message_text="qué criterios tengo?")
    intents = gateway.schema.get("_intents")
    assert isinstance(intents, list)
    names = {item["name"] for item in intents}
    assert names == {
        "consulta",
        "refinamiento",
        "comparacion",
        "feedback",
        "fuera_de_alcance",
    }
    assert "intent" in gateway.schema


def test_compile_normalizes_canonical_keys() -> None:
    compiler = _compiler(
        replies={
            _PROMPT: {
                "intent": "refinamiento",
                "parameters": [
                    {"key": "presupuesto", "value": "900", "confidence": 0.9}
                ],
                "high_impact_missing": ["zona"],
                "contradictions": [],
            }
        }
    )
    compilation = compiler.compile(message_text="subí el presupuesto a 900")
    assert compilation.parameters[0].key == "budget"
    assert compilation.high_impact_missing == ("zona",)


def test_compile_gateway_failure_is_typed() -> None:
    class FailingGateway:
        def generate_structured(self, **kwargs: object) -> object:
            from umbral.application.agent.contracts import ModelResult

            return ModelResult(
                content=None,
                model_version="local-fake",
                status="error",
                latency_ms=1,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                error_code="agent.provider_timeout",
            )

    compiler = _compiler(replies={}, gateway=FailingGateway())  # type: ignore[arg-type]
    with pytest.raises(IntentCompilationFailed):
        compiler.compile(message_text="hola")
