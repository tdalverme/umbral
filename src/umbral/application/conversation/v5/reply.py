"""Effect-grounded V5 reply composition with deterministic fallback.

The composer consumes only ``ConversationTurnResultV5``: it never sees
proposed acts without outcomes. Managed text comes from the model gateway and
is validated against ``reply-schema-v5.json``; on provider or schema failure
the reply falls back to deterministic Spanish text derived from actual
outcomes and reason codes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

import jsonschema  # type: ignore[import-untyped]

from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.v5.contracts import (
    ConversationTurnResultV5,
    OutcomeStatusV5,
)

ReplySourceV5 = Literal["managed", "deterministic_fallback"]


@dataclass(frozen=True, slots=True)
class ReplyOutcomeV5:
    act_id: str
    status: OutcomeStatusV5
    reason_code: str | None = None
    object_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ReplyV5:
    text: str
    outcomes: tuple[ReplyOutcomeV5, ...]
    verified_refs: tuple[str, ...]
    source: ReplySourceV5


class ReplyComposerV5:
    """Composes a reply strictly from executed turn outcomes."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        schema: Mapping[str, object],
        prompt_version: str,
        model_version: str,
        reply_schema_version: str = "conversation-reply-v5",
    ) -> None:
        self.gateway = gateway
        self.schema = schema
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.reply_schema_version = reply_schema_version

    def compose(self, result: ConversationTurnResultV5) -> ReplyV5:
        outcomes = tuple(
            ReplyOutcomeV5(
                act_id=item.act_id,
                status=item.status,
                reason_code=item.reason_code,
                object_ref=item.object_ref,
            )
            for item in result.outcomes
        )
        verified_refs = _verified_refs(result)
        if result.failure_stage is not None:
            return ReplyV5(
                _fallback_text(result),
                outcomes,
                verified_refs,
                "deterministic_fallback",
            )
        text = self._managed_text(result, outcomes, verified_refs)
        if text is None:
            return ReplyV5(
                _fallback_text(result),
                outcomes,
                verified_refs,
                "deterministic_fallback",
            )
        return ReplyV5(text, outcomes, verified_refs, "managed")

    def _managed_text(
        self,
        result: ConversationTurnResultV5,
        outcomes: tuple[ReplyOutcomeV5, ...],
        verified_refs: tuple[str, ...],
    ) -> str | None:
        messages: tuple[Mapping[str, object], ...] = (
            {
                "role": "system",
                "content": (
                    "Redactá una respuesta breve en español sobre los resultados "
                    "de este turno. Nunca inventes hechos: basate solo en los "
                    "outcomes listados y usa únicamente los refs verificables "
                    "provistos."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "outcomes": [
                            asdict(item) for item in outcomes
                        ],
                        "verified_refs": list(verified_refs),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        )
        gateway_result = self.gateway.generate_structured(
            messages=messages,
            schema=dict(self.schema),
            schema_version=self.reply_schema_version,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )
        if gateway_result.status != "success" or gateway_result.content is None:
            return None
        content = gateway_result.content
        try:
            jsonschema.validate(content, self.schema)
        except jsonschema.ValidationError:
            return None
        text = content.get("text")
        if not isinstance(text, str) or not text:
            return None
        return text


def _verified_refs(result: ConversationTurnResultV5) -> tuple[str, ...]:
    refs: list[str] = []
    for item in result.outcomes:
        if item.status == "applied" and item.object_ref:
            if item.object_ref not in refs:
                refs.append(item.object_ref)
    return tuple(refs[:10])


_REJECTION_TEXT = {
    "request.unsupported": "No puedo realizar esa operación.",
    "feedback.listing_not_authorized": "No puedo registrar ese feedback.",
    "desire.not_active": "Ese deseo no está activo.",
    "desire.ambiguous": "Tenés varios deseos similares; aclarame cuál querés cambiar.",
    "radar.not_bound": "Todavía no tenés un radar creado.",
    "radar.already_bound": "Ya tenés un radar activo.",
    "filter.not_active": "Ese filtro no está activo.",
    "act.missing_evidence": "No entendí bien tu pedido.",
    "act.untrusted_evidence": "No puedo usar ese contenido.",
    "capability.not_allowed": "Esa operación no está habilitada.",
    "execution.stale_context": "Tu información cambió; necesito que confirmes.",
    "execution.reconciliation_required": (
        "Hubo un problema al procesar; intentá de nuevo."
    ),
}


def _fallback_text(result: ConversationTurnResultV5) -> str:
    if result.failure_stage is not None:
        return "No pude procesar tu mensaje en este momento."
    lines: list[str] = []
    for item in result.outcomes:
        if item.status == "applied":
            lines.append("Listo.")
        elif item.status == "pending":
            lines.append("Quedó pendiente de tu confirmación.")
        elif item.status == "rejected":
            lines.append(
                _REJECTION_TEXT.get(
                    item.reason_code or "", "No pude completar esa acción."
                )
            )
        elif item.status == "needs_clarification":
            lines.append("Necesito que aclares un detalle para continuar.")
        else:
            lines.append("Esa acción no se ejecutó.")
    return " ".join(lines) if lines else "No pude procesar tu mensaje."