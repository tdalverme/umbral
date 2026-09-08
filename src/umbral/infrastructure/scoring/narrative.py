"""Managed, bounded adapter for selected-opportunity narrative copy."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import jsonschema  # type: ignore[import-untyped]

from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.voice_check import lint_voice
from umbral.application.scoring.contracts import ExplanationNarrativeContext
from umbral.application.scoring.narrative import (
    ExplanationNarrative,
    deterministic_narrative,
)

_TECHNICAL_COPY_RE = re.compile(
    r"\b(?:criterio|criterios|evidencia|evidencias|matcher|ranking|"
    r"normalizad[oa]s?|arquitectura|modelo|ia)\b",
    re.IGNORECASE,
)
_UNSAFE_GEOGRAPHY_RE = re.compile(
    r"\b(?:perfect[oa]?|ideal|safe|segur[oa]|silent|silencios?[oa]?|"
    r"garantizad[oa])\b"
    r"|\b(?:no hay|sin|libre de|ausencia de)\s+(?:ruido|tr[aá]fico|"
    r"crimen(?:es)?|delitos?|inseguridad|violencia)\b"
    r"|\b(?:zona|barrio|entorno|[áa]rea)\s+(?:segur[oa]|silencios[oa]|"
    r"tranquil[oa])\b",
    re.IGNORECASE,
)
_RAW_KEY_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]*\b", re.IGNORECASE)
_PRICE_COPY_RE = re.compile(r"(?:USD|ARS|\$)\s?[\d.]+", re.IGNORECASE)


class ManagedExplanationNarrativeWriter:
    """Accept only schema-valid, context-authorized presentation copy."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        schema: Mapping[str, object],
        prompt_version: str,
        model_version: str,
        schema_version: str = "explanation-narrative-v1",
        system_prompt: str | None = None,
    ) -> None:
        self.gateway = gateway
        self.schema = schema
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.schema_version = schema_version
        self.system_prompt = system_prompt or _load_narrative_prompt()

    def write(self, context: ExplanationNarrativeContext) -> ExplanationNarrative:
        fallback = deterministic_narrative(
            context,
            prompt_version=self.prompt_version,
        )
        try:
            result = self.gateway.generate_structured(
                messages=_messages(self.system_prompt, context),
                schema=self.schema,
                schema_version=self.schema_version,
                prompt_version=self.prompt_version,
                model_version=self.model_version,
            )
        except Exception:
            return fallback
        if result.status != "success" or result.content is None:
            return fallback
        content = result.content
        if not _valid_content(content, self.schema, context):
            return fallback
        return ExplanationNarrative(
            text=cast(str, content["text"]),
            used_criteria=tuple(cast(list[str], content["used_criteria"])),
            used_evidence_refs=tuple(cast(list[str], content["used_evidence_refs"])),
            source="managed",
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )


def _messages(
    system_prompt: str,
    context: ExplanationNarrativeContext,
) -> tuple[Mapping[str, object], ...]:
    return (
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "listing": context.listing,
                    "active_priorities": context.active_priorities,
                    "reasons": context.reasons,
                    "tradeoffs": context.tradeoffs,
                    "unknowns": context.unknowns,
                    "geography": [
                        {
                            "label": fact.label,
                            "fact": fact.value,
                            "evidence_refs": [fact.source_ref],
                        }
                        for fact in context.geography
                    ],
                    "price_changes": context.price_changes,
                    "allowed_criteria": context.allowed_criteria,
                    "allowed_evidence_refs": context.allowed_evidence_refs,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    )


def _valid_content(
    content: Mapping[str, object],
    schema: Mapping[str, object],
    context: ExplanationNarrativeContext,
) -> bool:
    try:
        jsonschema.validate(content, schema)
    except jsonschema.ValidationError:
        return False
    text = content.get("text")
    criteria = content.get("used_criteria")
    evidence_refs = content.get("used_evidence_refs")
    if not isinstance(text, str):
        return False
    if not isinstance(criteria, list) or not criteria:
        return False
    if not all(
        isinstance(value, str)
        and value in context.allowed_criteria
        and value in context.criterion_evidence_refs
        for value in criteria
    ):
        return False
    criterion_refs = {
        ref
        for criterion in criteria
        for ref in context.criterion_evidence_refs[criterion]
    }
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(
        isinstance(value, str)
        and value in context.allowed_evidence_refs
        and (
            value in criterion_refs
            or (value == "listing_field:price" and bool(context.price_changes))
        )
        for value in evidence_refs
    ):
        return False
    if _TECHNICAL_COPY_RE.search(text) or _UNSAFE_GEOGRAPHY_RE.search(text):
        return False
    if _RAW_KEY_RE.search(text):
        return False
    if not _claims_match_context(text, criteria, evidence_refs, context):
        return False
    return not lint_voice(text)


def _claims_match_context(
    text: str,
    criteria: list[object],
    evidence_refs: list[object],
    context: ExplanationNarrativeContext,
) -> bool:
    lowered = text.casefold()
    packets = (*context.reasons, *context.tradeoffs, *context.unknowns)
    if _PRICE_COPY_RE.search(text) and not context.price_changes:
        return False
    for criterion in criteria:
        if not isinstance(criterion, str):
            return False
        packet = next(
            (item for item in packets if item.get("criterion_key") == criterion),
            None,
        )
        if packet is None:
            refs = set(context.criterion_evidence_refs.get(criterion, ()))
            packet = next(
                (item for item in packets if refs.intersection(_packet_refs(item))),
                None,
            )
        criterion_refs = set(context.criterion_evidence_refs.get(criterion, ()))
        submitted_refs = {
            value for value in evidence_refs if isinstance(value, str)
        }
        if packet is None and not any(
            fact.criterion_key == criterion
            and fact.value.casefold() in lowered
            and fact.source_ref in submitted_refs
            for fact in context.geography
        ):
            return False
        if not criterion_refs or not criterion_refs.intersection(submitted_refs):
            return False
        if packet is not None:
            packet_refs = set(_packet_refs(packet))
            if not packet_refs.intersection(submitted_refs):
                return False
            label = packet.get("label")
            if not isinstance(label, str) or label.casefold() not in lowered:
                return False
            fact = packet.get("fact")
            if isinstance(fact, str) and fact.casefold() not in lowered:
                return False
        elif not any(
            fact.criterion_key == criterion
            and fact.value.casefold() in lowered
            and fact.source_ref in submitted_refs
            for fact in context.geography
        ):
            return False
    for fact in context.geography:
        if fact.criterion_key in criteria and fact.value.casefold() not in lowered:
            return False
    if re.search(r"(?:baj[oó]|pas[oó]|subi[oó]|aument[oó])", lowered):
        if not context.price_changes:
            return False
        if (
            not isinstance(evidence_refs, list)
            or "listing_field:price" not in evidence_refs
        ):
            return False
        if not all(
            _price_mentioned(change, text) for change in context.price_changes
        ):
            return False
    if re.search(r"\b(?:balcón|pileta|piscina|terraza|patio|cochera)\b", lowered):
        authorized_labels = {
            str(item.get("label", "")).casefold()
            for item in packets
        }
        if not any(
            term in authorized_labels
            for term in (
                "balcón",
                "pileta",
                "piscina",
                "terraza",
                "patio",
                "cochera",
            )
        ):
            return False
    return True


def _price_mentioned(change: Mapping[str, object], text: str) -> bool:
    before = change.get("before")
    after = change.get("after")
    currency = change.get("currency")
    if not isinstance(before, (int, float)) or isinstance(before, bool):
        return False
    if not isinstance(after, (int, float)) or isinstance(after, bool):
        return False
    if not isinstance(currency, str):
        return False
    def token(value: int | float) -> str:
        return f"{value:,.0f}".replace(",", ".")
    return all(f"{currency} {token(value)}" in text for value in (before, after))


def _packet_refs(packet: Mapping[str, object]) -> tuple[str, ...]:
    refs = packet.get("evidence_refs")
    if not isinstance(refs, (tuple, list)):
        return ()
    return tuple(ref for ref in refs if isinstance(ref, str))


def _load_narrative_prompt() -> str:
    module_root = Path(__file__).resolve().parents[2]
    prompt = _read_text(module_root / "agent" / "prompts" / "explanation-narrative.md")
    product = _product_voice_context(_read_text(module_root.parents[1] / "PRODUCT.md"))
    if prompt and product:
        return (
            f"{prompt}\n\n## Contexto de producto — PRODUCT.md\n\n{product}\n\n"
            "Este contexto es interno: aplicá su voz, sin exponer etiquetas internas."
        )
    return prompt


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _product_voice_context(product: str) -> str:
    sections = {
        "## Product Purpose": ("**Por qué existe:",),
        "## Brand Commitments": (
            "**Personalidad y voz:",
            "**Principios de escritura y patrones de agente",
            "**Reglas para explicar coincidencias:",
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
