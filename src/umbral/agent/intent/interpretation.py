"""Ordered multi-act interpretation compilation v4 (UM-H4-022, R-01).

The model only fills the structured ``conversation-interpretation-v4`` payload;
the planner (application/conversation/policy) decides routing and durable
state deterministically. This compiler validates act kinds against the
published vocabulary and never invents acts.
"""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.contracts import (
    ConversationAct,
    TurnInterpretation,
    is_known_act_kind,
)


class InterpretationUnclassified(ValueError):
    """The gateway produced an act outside the published vocabulary."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"interpretation_unclassified: {reason}")


class InterpretationCompilationFailed(ValueError):
    """The model gateway did not produce a valid structured interpretation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"interpretation_failed: {reason}")


class InterpretationCompiler:
    """Compiles one message into ordered multi-acts over the model gateway."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        schema: Mapping[str, object],
        prompt_version: str,
        model_version: str,
        interpretation_version: str = "conversation-interpretation-v4",
        max_acts: int = 6,
    ) -> None:
        self.gateway = gateway
        self.schema = schema
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.interpretation_version = interpretation_version
        self.max_acts = max_acts

    def interpret(
        self,
        *,
        message_text: str,
        pending_action: Mapping[str, object] | None,
        correlation_id: object | None = None,
    ) -> TurnInterpretation:
        messages: list[Mapping[str, object]] = []
        if pending_action:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Existe una accion pendiente que debe resolverse antes "
                        "de interpretar cualquier acto nuevo; si el mensaje "
                        "confirma, rechaza o edita esa accion, emite "
                        "resolve_pending como primer acto."
                    ),
                }
            )
        messages.append({"role": "user", "content": message_text})
        result = self.gateway.generate_structured(
            messages=tuple(messages),
            schema=dict(self.schema),
            schema_version=self.interpretation_version,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )
        if result.status != "success" or result.content is None:
            raise InterpretationCompilationFailed(
                result.error_code or "agent.interpretation_failed"
            )
        return self._interpretation_from_data(result.content)

    def _interpretation_from_data(
        self, data: Mapping[str, object]
    ) -> TurnInterpretation:
        raw_acts = data.get("acts")
        if not isinstance(raw_acts, list):
            raise InterpretationCompilationFailed("missing acts")
        acts: list[ConversationAct] = []
        seen: set[str] = set()
        for item in raw_acts[: self.max_acts]:
            if not isinstance(item, Mapping):
                raise InterpretationCompilationFailed("invalid act shape")
            act_id = item.get("act_id")
            kind = item.get("kind")
            if not isinstance(act_id, str) or not act_id:
                raise InterpretationCompilationFailed("act_id required")
            if act_id in seen:
                raise InterpretationCompilationFailed("duplicate act_id")
            seen.add(act_id)
            if not isinstance(kind, str) or not is_known_act_kind(kind):
                raise InterpretationUnclassified(str(kind))
            acts.append(
                ConversationAct(
                    act_id=act_id,
                    kind=kind,
                    target=_mapping(item.get("target")),
                    payload=_mapping(item.get("payload")),
                    confidence=_confidence(item.get("confidence")),
                )
            )
        ambiguity = _mapping_or_none(data.get("ambiguity"))
        return TurnInterpretation(acts=tuple(acts), ambiguity=ambiguity)

    def _empty_interpretation(self) -> TurnInterpretation:
        return TurnInterpretation(acts=())


def _mapping(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _mapping_or_none(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    return dict(value) if isinstance(value, Mapping) else None


def _confidence(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    return 1.0