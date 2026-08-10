"""Intent compilation over the model gateway (UM-H4-017, R-01/R-02)."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.agent.intent.contracts import (
    IntentCompilation,
    IntentCompilationFailed,
    IntentContract,
    IntentContradiction,
    IntentParameter,
    IntentUnclassified,
)
from umbral.application.agent.ports import ModelGateway


class IntentCompiler:
    """Classifies a message into exactly one intent and extracts parameters.

    The model only fills the ``output`` section of intent-schema-v3; the
    allowed-tools policy comes from the machine-checkable contract, not from
    the model (R-02).
    """

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        contract: IntentContract,
        prompt_version: str,
        model_version: str,
    ) -> None:
        self.gateway = gateway
        self.contract = contract
        self.prompt_version = prompt_version
        self.model_version = model_version

    def compile(
        self,
        *,
        message_text: str,
        clarification_context: Mapping[str, object] | None = None,
    ) -> IntentCompilation:
        messages = [
            {"role": "user", "content": message_text},
        ]
        if clarification_context:
            pending = clarification_context.get("pending_params")
            pending_text = (
                ", ".join(str(item) for item in pending)
                if isinstance(pending, list)
                else ""
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "El usuario esta respondiendo la aclaracion sobre: "
                        f"{pending_text}. Integra la respuesta a esos parametros."
                    ),
                }
            )
        result = self.gateway.generate_structured(
            messages=tuple(messages),
            schema=self.contract.output_schema,
            schema_version=self.contract.schema_version,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )
        if result.status != "success" or result.content is None:
            raise IntentCompilationFailed()
        raw = result.content
        intent = raw.get("intent")
        if not isinstance(intent, str) or intent not in self.contract.known_intents():
            raise IntentUnclassified()
        raw_parameters = raw.get("parameters")
        raw_missing = raw.get("high_impact_missing")
        raw_contradictions = raw.get("contradictions")
        parameters = tuple(
            IntentParameter(
                key=_string(item, "key"),
                value=_string(item, "value"),
                confidence=_number(item.get("confidence"), 0.0),
            )
            for item in (raw_parameters if isinstance(raw_parameters, list) else [])
            if isinstance(item, Mapping) and "key" in item and "value" in item
        )
        missing = tuple(
            str(item)
            for item in (raw_missing if isinstance(raw_missing, list) else [])
            if isinstance(item, str)
        )
        contradictions = tuple(
            IntentContradiction(
                key=_string(item, "key"),
                current_value=_string(item, "current_value"),
                requested=_string(item, "requested"),
            )
            for item in (
                raw_contradictions if isinstance(raw_contradictions, list) else []
            )
            if isinstance(item, Mapping) and "key" in item
        )
        return IntentCompilation(
            intent=intent,
            parameters=parameters,
            high_impact_missing=missing,
            contradictions=contradictions,
            allowed_tools=self.contract.allowed_tools_for(intent),
        )


def _string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return value if isinstance(value, str) else str(value or "")


def _number(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default
