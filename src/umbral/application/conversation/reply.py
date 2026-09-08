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
from dataclasses import dataclass
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


_PREFERENCE_TARGETS = {
    "luminosidad": "departamentos con buena luz natural",
    "ruido_ambiental": "lugares con poco ruido",
    "vida_nocturna": "zonas con poca actividad nocturna",
    "calma_residencial": "zonas tranquilas y de casas bajas",
    "acceso_transporte": "buen acceso al transporte",
}
_PRIORITY_LABELS = {
    "low": "considerar",
    "medium": "priorizar",
    "high": "priorizar especialmente",
    "essential": "priorizar especialmente",
}


def _preference_target(concept: ReplyConcept) -> str:
    return _PREFERENCE_TARGETS.get(concept.concept_ref, "lo que me pediste")


def _unique_concepts(
    concepts: tuple[ReplyConcept, ...],
) -> tuple[ReplyConcept, ...]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ReplyConcept] = []
    for concept in concepts:
        key = (concept.concept_ref, concept.polarity, concept.intensity)
        if key not in seen:
            seen.add(key)
            unique.append(concept)
    return tuple(unique)


def _managed_outcome(item: ReplyOutcome) -> dict[str, object]:
    """Expose only safe, human-facing context to the reply writer."""
    outcome: dict[str, object] = {
        "status": item.status,
        "effect": item.effect,
        "concepts": [
            {
                "label": _preference_target(concept),
                "polarity": concept.polarity,
                "priority": _PRIORITY_LABELS[concept.intensity],
            }
            for concept in item.concepts
        ],
    }
    if item.ordinal is not None:
        outcome["ordinal"] = item.ordinal
    if item.total is not None:
        outcome["total"] = item.total
    return outcome


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
    """Carga la voz versionada y el contexto de producto desde PRODUCT.md.

    Fallback a _DEFAULT_SYSTEM_PROMPT si el archivo no existe (tests aislados
    o migraciones). El prompt contiene las reglas ejecutables y PRODUCT.md
    conserva la fuente de verdad de propósito, posicionamiento y voz.
    """
    module_root = Path(__file__).resolve().parents[2]
    prompt = _read_text(module_root / "agent" / "prompts" / "reply.md")
    product = _product_voice_context(_read_text(module_root.parents[1] / "PRODUCT.md"))
    if prompt and product:
        return (
            f"{prompt}\n\n"
            "## Contexto de producto — PRODUCT.md\n\n"
            f"{product}\n\n"
            "Este contexto es interno: aplicá su voz y propósito, pero no "
            "expongas etiquetas técnicas ni clasificaciones internas."
        )
    return prompt or _DEFAULT_SYSTEM_PROMPT


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _product_voice_context(product: str) -> str:
    """Select the voice and purpose excerpts needed by a reply writer."""
    sections = {
        "## Product Purpose": ("**Por qué existe:", "**Qué significa éxito:"),
        "## Positioning": ("**Mecanismo diferencial",),
        "## Brand Commitments": (
            "**Plataforma de marca:",
            "**Personalidad y voz:",
            "**Principios de escritura y patrones de agente",
            "**Arquitectura verbal:",
        ),
        "## Product Principles": None,
        "## Accessibility & Inclusion": ("- **Inclusión y lenguaje:",),
    }
    selected: list[str] = []
    active: str | None = None
    for line in product.splitlines():
        if line.startswith("## "):
            active = line if line in sections else None
            if active:
                selected.append(line)
            continue
        prefixes = sections.get(active) if active else None
        if active == "## Product Principles" or (
            prefixes and any(line.startswith(prefix) for prefix in prefixes)
        ):
            selected.append(line)
    return "\n".join(selected).strip()


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
        # State-changing filter outcomes and unresolved desires have canonical
        # wording that must preserve confirmation/rejection semantics exactly.
        if any(item.effect not in {"other", "preference.applied"} for item in outcomes):
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
                            _managed_outcome(item) for item in outcomes
                        ],
                        "verified_refs": list(verified_refs),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        )
        try:
            gateway_result = self.gateway.generate_structured(
                messages=messages,
                schema=dict(self.schema),
                schema_version=self.reply_schema_version,
                prompt_version=self.prompt_version,
                model_version=self.model_version,
            )
        except Exception:
            return None
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
        # Guard de voz: si el LLM viola VOZ-06/07/08 hard, descartar
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
                concepts = _unique_concepts(
                    tuple(
                        ReplyConcept(
                            concept_ref=link.concept_ref,
                            polarity=link.polarity,
                            intensity=link.intensity,
                        )
                        for link in command.concept_links
                    )
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


def _preference_lines(concepts: tuple[ReplyConcept, ...]) -> list[str]:
    unique = _unique_concepts(concepts)
    if not unique:
        return []
    targets = [_preference_target(concept) for concept in unique]
    if len(targets) == 1:
        target_text = targets[0]
    elif len(targets) == 2:
        target_text = " y ".join(targets)
    else:
        target_text = f"{', '.join(targets[:-1])} y {targets[-1]}"
    return [
        "Anotado. Voy a tener en cuenta "
        f"{target_text} al ordenar las opciones."
    ]
