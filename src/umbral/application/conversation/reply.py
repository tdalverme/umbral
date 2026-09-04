"""Effect-grounded V5 reply composition with deterministic fallback.

The composer consumes only ``ConversationTurnResult``: it never sees
proposed acts without outcomes. Managed text comes from the model gateway and
is validated against ``reply-schema.json``; on provider or schema failure
the reply falls back to deterministic Spanish text derived from actual
outcomes and reason codes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import jsonschema  # type: ignore[import-untyped]

from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.contracts import (
    ConversationTurnResult,
    OutcomeStatus,
    RecordDesireCommand,
)

ReplySource = Literal["managed", "deterministic_fallback"]
ReplyEffect = Literal[
    "other",
    "preference.applied",
    "desire.remembered_unresolved",
    "filter.requires_confirmation",
    "filter.approved",
    "filter.rejected",
]


@dataclass(frozen=True, slots=True)
class ReplyConcept:
    """Trusted semantic detail that the reply may acknowledge."""

    concept_ref: str
    polarity: Literal["positive", "negative"]
    intensity: Literal["low", "medium", "high", "essential"]


@dataclass(frozen=True, slots=True)
class ReplyOutcome:
    act_id: str
    status: OutcomeStatus
    reason_code: str | None = None
    object_ref: str | None = None
    effect: ReplyEffect = "other"
    concepts: tuple[ReplyConcept, ...] = ()
    ordinal: int | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    outcomes: tuple[ReplyOutcome, ...]
    verified_refs: tuple[str, ...]
    source: ReplySource


_DEFAULT_SYSTEM_PROMPT = (
    "Redactá una respuesta breve en español sobre los resultados "
    "de este turno. Nunca inventes hechos: basate solo en los "
    "outcomes listados y usa únicamente los refs verificables "
    "provistos."
)

_VOICE_HARD_VIOLATIONS = (
    "VOZ-06",
    "VOZ-07:emoji",
    "VOZ-07:tech_jargon",
    "VOZ-08:certainty_without_evidence",
    "VOZ-07:multiple_exclamations",
    "VOZ-07:too_many_exclamations",
)


def _load_reply_prompt() -> str:
    """Carga voice-v1 desde src/umbral/agent/prompts/reply.md.

    Fallback a _DEFAULT_SYSTEM_PROMPT si el archivo no existe (tests aislados
    o migraciones). El prompt versionado es la fuente de verdad de voz; el
    fallback mantiene grounding minimo.
    """
    try:
        path = (
            Path(__file__).resolve().parents[3]
            / "agent"
            / "prompts"
            / "reply.md"
        )
        text = path.read_text(encoding="utf-8")
        # Enviar el archivo completo: contiene Rol, Reglas grounded+voz y
        # Patrones aprobados (voice-v1). El modelo recibe la guía ejecutable.
        if text.strip():
            return text
    except OSError:
        pass
    return _DEFAULT_SYSTEM_PROMPT


class ReplyComposer:
    """Composes a reply strictly from executed turn outcomes."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        schema: Mapping[str, object],
        prompt_version: str,
        model_version: str,
        reply_schema_version: str = "conversation-reply",
        system_prompt: str | None = None,
    ) -> None:
        self.gateway = gateway
        self.schema = schema
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.reply_schema_version = reply_schema_version
        self._system_prompt = system_prompt or _load_reply_prompt()

    def compose(self, result: ConversationTurnResult) -> Reply:
        outcomes = _reply_outcomes(result)
        verified_refs = _verified_refs(result)
        if result.failure_stage is not None:
            return Reply(
                _fallback_text(result),
                outcomes,
                verified_refs,
                "deterministic_fallback",
            )
        if any(item.effect != "other" for item in outcomes):
            return Reply(
                _fallback_text(result),
                outcomes,
                verified_refs,
                "deterministic_fallback",
            )
        text = self._managed_text(result, outcomes, verified_refs)
        if text is None:
            return Reply(
                _fallback_text(result),
                outcomes,
                verified_refs,
                "deterministic_fallback",
            )
        return Reply(text, outcomes, verified_refs, "managed")

    def _managed_text(
        self,
        result: ConversationTurnResult,
        outcomes: tuple[ReplyOutcome, ...],
        verified_refs: tuple[str, ...],
    ) -> str | None:
        messages: tuple[Mapping[str, object], ...] = (
            {
                "role": "system",
                "content": self._system_prompt,
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
        # Guard de voz voice-v1: si el LLM viola VOZ-06/07/08 hard, descartar
        # y caer a deterministic_fallback (grounded sereno).
        try:
            from umbral.application.conversation.voice_check import (
                check_grounded,
                lint_voice,
            )

            violations = lint_voice(text)
            if any(
                v.startswith(h) for v in violations for h in _VOICE_HARD_VIOLATIONS
            ):  # noqa: E501
                return None
            # Grounded: rejected/pending mal contado como applied
            grounded = check_grounded(
                text,
                [
                    {"status": o.status, "reason_code": o.reason_code}
                    for o in outcomes
                ],
            )
            if grounded:
                return None
        except Exception:
            # Nunca romper el compose por un lint roto; dejar pasar el texto
            pass
        return text


def _verified_refs(result: ConversationTurnResult) -> tuple[str, ...]:
    refs: list[str] = []
    for item in result.outcomes:
        if item.status == "applied" and item.object_ref:
            if item.object_ref not in refs:
                refs.append(item.object_ref)
    return tuple(refs[:10])


def _reply_outcomes(
    result: ConversationTurnResult,
) -> tuple[ReplyOutcome, ...]:
    """Project durable effects into the reply's least-authority context.

    This projection uses only typed commands, execution receipts and the
    reloaded pending head. It deliberately does not inspect the user message
    or reinterpret an act's natural-language evidence.
    """
    executed_by_act = {item.act_id: item for item in result.executed}
    commands_by_act = (
        {item.act_id: item for item in result.plan.commands}
        if result.plan is not None
        else {}
    )
    projected: list[ReplyOutcome] = []
    has_active_pending = False
    for outcome in result.outcomes:
        executed = executed_by_act.get(outcome.act_id)
        effect: ReplyEffect = "other"
        concepts: tuple[ReplyConcept, ...] = ()
        ordinal: int | None = None
        total: int | None = None

        if executed is not None and executed.effect_key == "desire.remembered":
            command = commands_by_act.get(outcome.act_id)
            if outcome.status == "applied" and isinstance(command, RecordDesireCommand):
                concepts = tuple(
                    ReplyConcept(
                        concept_ref=link.concept_ref,
                        polarity=link.polarity,
                        intensity=link.intensity,
                    )
                    for link in command.concept_links
                )
                effect = (
                    "preference.applied"
                    if concepts
                    else "desire.remembered_unresolved"
                )
        elif executed is not None and executed.effect_key == "pending.resolved":
            if outcome.status == "applied":
                effect = "filter.approved"
            elif outcome.status == "rejected" and outcome.reason_code == "user":
                effect = "filter.rejected"
        elif (
            outcome.status == "pending"
            and outcome.reason_code == "filter.requires_confirmation"
            and result.context.pending_action is not None
            and outcome.act_id == result.context.pending_action.act_id
        ):
            effect = "filter.requires_confirmation"
            ordinal = result.context.pending_action.ordinal
            total = result.context.pending_action.total
            has_active_pending = True

        projected.append(
            ReplyOutcome(
                act_id=outcome.act_id,
                status=outcome.status,
                reason_code=outcome.reason_code,
                object_ref=outcome.object_ref,
                effect=effect,
                concepts=concepts,
                ordinal=ordinal,
                total=total,
            )
        )
    pending = result.context.pending_action
    created_pending = any(item.status == "pending" for item in result.outcomes)
    resolved_pending = any(
        item.effect_key == "pending.resolved" for item in result.executed
    )
    if (
        pending is not None
        and (created_pending or resolved_pending)
        and not has_active_pending
    ):
        projected.append(
            ReplyOutcome(
                act_id=pending.act_id,
                status="pending",
                reason_code="filter.requires_confirmation",
                effect="filter.requires_confirmation",
                ordinal=pending.ordinal,
                total=pending.total,
            )
        )
    return tuple(projected)


_REJECTION_TEXT = {
    "request.unsupported": (
        "No puedo realizar esa operación. Si querés, decime qué querés ajustar "
        "del radar y lo vemos."
    ),
    "feedback.listing_not_authorized": (
        "No puedo registrar ese feedback porque no tengo esa propiedad en tu foco "
        "actual. Abrila y probá de nuevo."
    ),
    "desire.not_active": (  # noqa: E501
        "Ese deseo no está activo en tu radar. ¿Querés que lo agregue?"
    ),
    "desire.ambiguous": (  # noqa: E501
        "Tenés varios deseos similares; aclarame cuál querés cambiar."
    ),
    "radar.not_bound": (
        "Todavía no tenés un radar creado. "  # noqa: E501
        "¿Querés que lo armemos con lo que me contaste?"  # noqa: E501
    ),
    "radar.already_bound": "Ya tenés un radar activo.",
    "filter.not_active": "Ese filtro no está activo en tu radar.",
    "act.missing_evidence": (  # noqa: E501
        "No entendí bien tu pedido. ¿Me lo decís con un ejemplo concreto?"
    ),
    "act.untrusted_evidence": "No puedo usar ese contenido como instrucción.",
    "capability.not_allowed": "Esa operación no está habilitada.",
    "execution.stale_context": (
        "Tu radar cambió mientras procesaba. Confirmame y lo intento de nuevo."
    ),
    "execution.reconciliation_required": (
        "Hubo un problema al procesar; intentá de nuevo."
    ),
}


def _fallback_text(result: ConversationTurnResult) -> str:
    if result.failure_stage is not None:
        return "No pude procesar tu mensaje en este momento."
    lines: list[str] = []
    for item in _reply_outcomes(result):
        if item.effect == "preference.applied":
            lines.extend(_preference_lines(item.concepts))
        elif item.effect == "desire.remembered_unresolved":
            lines.append(
                "Lo dejé registrado, pero por ahora no cambia el orden de las "
                "oportunidades."
            )
        elif item.effect == "filter.approved":
            lines.append("El cambio anterior quedó confirmado.")
        elif item.effect == "filter.rejected":
            lines.append("El cambio anterior quedó rechazado.")
        elif item.effect == "filter.requires_confirmation":
            lines.append(
                "¿Confirmás este cambio del radar "
                f"({item.ordinal or 1} de {item.total or 1})?"
            )
        elif item.status == "applied":
            lines.append("Listo.")
        elif item.status == "pending":
            # A pending outcome that no longer has a durable head was resolved
            # later in this same graph run, so it must not be asked again.
            if result.context.pending_action is not None or any(
                executed.effect_key == "pending.resolved"
                for executed in result.executed
            ):
                continue
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


_INTENSITY_WORDS = {
    "low": "leve",
    "medium": "moderada",
    "high": "alta",
    "essential": "prioritaria",
}


def _preference_lines(concepts: tuple[ReplyConcept, ...]) -> list[str]:
    lines: list[str] = []
    for concept in concepts:
        label = concept.concept_ref.replace("_", " ")
        intensity = _INTENSITY_WORDS[concept.intensity]
        if concept.polarity == "negative":
            lines.append(
                f"Voy a tener en cuenta evitar {label} como preferencia {intensity}."
            )
        else:
            lines.append(
                f"Voy a tener en cuenta {label} como preferencia {intensity}."
            )
    return lines
