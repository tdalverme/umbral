"""Managed, bounded adapter for selected-opportunity narrative copy."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import jsonschema  # type: ignore[import-untyped]

from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.voice_check import lint_voice
from umbral.application.scoring.contracts import ExplanationNarrativeContext
from umbral.application.scoring.narrative import (
    ExplanationNarrative,
    deterministic_narrative,
)

_TECHNICAL_COPY_RE = re.compile(
    r"\b(?:criterio|criterios|matcher|ranking|"
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
_PRICE_CHANGE_RE = re.compile(
    r"\b(?:baj[oó]|reduj[oó]|sub[ií]|aument[oó]|pas[oó])\b\s+de\b"
    r"|\bprecio\s+(?:baj[oó]|sub[ií]|aument[oó]|pas[oó])\b",
    re.IGNORECASE,
)
_MATCH_CUE_RE = re.compile(
    r"\b(?:encaja|suma|compensa|alinead[oa]|mejora|buena pinta)\b",
    re.IGNORECASE,
)
_TRADEOFF_CUE_RE = re.compile(
    r"\b(?:contra|a cambio|menos|aunque|revisar|sacrificar)\b",
    re.IGNORECASE,
)
_KNOWN_PROPERTY_TERM_RE = re.compile(
    r"\b(?:balc[oó]n|vista|r[ií]o|cocina|living|escritorio|"
    r"dormitorios?|ba[ñn]os?|cochera|piscina|expensas|orientaci[oó]n|"
    r"estado|luminosidad|luz|ruido|tr[aá]fico|subte|tren|parque|"
    r"caf[eé]s?|restaurantes?|servicios|superficie)\b",
    re.IGNORECASE,
)
_DESCRIPTOR_STOPWORDS = frozenset(
    {
        "algo",
        "algunos",
        "bastante",
        "buena",
        "bueno",
        "cerca",
        "con",
        "del",
        "de",
        "el",
        "la",
        "las",
        "los",
        "más",
        "mayor",
        "menor",
        "para",
        "una",
        "uno",
        "unos",
    }
)
_WORD_RE = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)

ClaimPlacement = Literal["match", "tradeoff", "unknown", "price"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _RenderedClaim:
    """One packet-backed claim used to validate managed output."""

    criterion_key: str | None
    evidence_refs: tuple[str, ...]
    placement: ClaimPlacement
    descriptor: str
    rendered: str


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
        except Exception as error:
            logger.warning(
                "explanation narrative fallback",
                extra={
                    "narrative_outcome": "fallback",
                    "narrative_reason": "gateway_exception",
                    "error_type": type(error).__name__,
                    "model_version": self.model_version,
                },
            )
            return fallback
        if result.status != "success" or result.content is None:
            logger.warning(
                "explanation narrative fallback",
                extra={
                    "narrative_outcome": "fallback",
                    "narrative_reason": "gateway_result",
                    "gateway_status": result.status,
                    "gateway_error_code": result.error_code,
                    "model_version": self.model_version,
                },
            )
            return fallback
        content = result.content
        if not _valid_content(content, self.schema, context):
            logger.warning(
                "explanation narrative fallback",
                extra={
                    "narrative_outcome": "fallback",
                    "narrative_reason": "validation_rejected",
                    "model_version": self.model_version,
                },
            )
            return fallback
        logger.info(
            "explanation narrative managed",
            extra={
                "narrative_outcome": "managed",
                "model_version": self.model_version,
            },
        )
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
    if not _claims_are_grounded(text, criteria, evidence_refs, context):
        return False
    return not lint_voice(text)


def _claims_are_grounded(
    text: str,
    criteria: list[object],
    evidence_refs: list[object],
    context: ExplanationNarrativeContext,
) -> bool:
    """Validate provenance and anchors without constraining the prose shape."""
    claims = _rendered_claims(criteria, evidence_refs, context)
    if claims is None:
        return False
    if _contains_untracked_property_term(text, claims):
        return False
    if _contains_untracked_match_cue(text, claims):
        return False
    if _mentions_ungrounded_price_change(text, evidence_refs, context):
        return False
    for claim in claims:
        if claim.placement == "price":
            if not _mentions_authorized_price_change(text, claim, context):
                return False
            continue
        if not _mentions_descriptor(text, claim.descriptor):
            return False
        if not _placement_is_consistent(text, claim):
            return False
    return True


def _contains_untracked_property_term(
    text: str,
    claims: tuple[_RenderedClaim, ...],
) -> bool:
    selected_terms = {
        term
        for claim in claims
        if claim.placement != "price"
        for term in _descriptor_terms(claim.descriptor)
    }
    return any(
        match.group(0).casefold() not in selected_terms
        for match in _KNOWN_PROPERTY_TERM_RE.finditer(text)
    )


def _contains_untracked_match_cue(
    text: str,
    claims: tuple[_RenderedClaim, ...],
) -> bool:
    return not any(claim.placement == "match" for claim in claims) and bool(
        _MATCH_CUE_RE.search(text)
    )


def _mentions_ungrounded_price_change(
    text: str,
    evidence_refs: list[object],
    context: ExplanationNarrativeContext,
) -> bool:
    return bool(_PRICE_CHANGE_RE.search(text)) and (
        "listing_field:price" not in evidence_refs or not context.price_changes
    )


def _mentions_authorized_price_change(
    text: str,
    claim: _RenderedClaim,
    context: ExplanationNarrativeContext,
) -> bool:
    del claim
    for change in context.price_changes:
        before = change.get("before")
        after = change.get("after")
        if not isinstance(before, (int, float)) or isinstance(before, bool):
            continue
        if not isinstance(after, (int, float)) or isinstance(after, bool):
            continue
        digits = re.sub(r"\D", "", text)
        if str(int(before)) not in digits or str(int(after)) not in digits:
            continue
        if after < before and re.search(r"\b(?:baj[oó]|reduj[oó])\b", text, re.I):
            return True
        if after > before and re.search(
            r"\b(?:sub[ií]|aument[oó]|pas[oó])\b", text, re.I
        ):
            return True
    return False


def _placement_is_consistent(text: str, claim: _RenderedClaim) -> bool:
    sentences = _sentences_for_descriptor(text, claim.descriptor)
    if not sentences:
        return False
    for sentence in sentences:
        has_match = bool(_MATCH_CUE_RE.search(sentence))
        has_tradeoff = bool(_TRADEOFF_CUE_RE.search(sentence))
        if claim.placement == "match" and has_tradeoff and not has_match:
            return False
        if claim.placement == "tradeoff" and has_match and not has_tradeoff:
            return False
        if claim.placement == "match" and re.search(
            r"\bno\s+(?:encaja|tiene|hay|es)\b", sentence, re.I
        ):
            return False
    return True


def _mentions_descriptor(text: str, descriptor: str) -> bool:
    terms = _descriptor_terms(descriptor)
    if not terms:
        return False
    text_terms = set(_WORD_RE.findall(text.casefold()))
    return any(term in text_terms for term in terms)


def _sentences_for_descriptor(text: str, descriptor: str) -> tuple[str, ...]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return tuple(
        sentence for sentence in sentences if _mentions_descriptor(sentence, descriptor)
    )


def _descriptor_terms(descriptor: str) -> tuple[str, ...]:
    return tuple(
        term
        for term in _WORD_RE.findall(descriptor.casefold())
        if len(term) > 2 and term not in _DESCRIPTOR_STOPWORDS
    )


def _rendered_claims(
    criteria: list[object],
    evidence_refs: list[object],
    context: ExplanationNarrativeContext,
) -> tuple[_RenderedClaim, ...] | None:
    selected_criteria = tuple(value for value in criteria if isinstance(value, str))
    submitted_refs = tuple(value for value in evidence_refs if isinstance(value, str))
    if len(selected_criteria) != len(set(selected_criteria)):
        return None
    if len(submitted_refs) != len(set(submitted_refs)):
        return None
    criterion_refs = {
        criterion: set(context.criterion_evidence_refs.get(criterion, ()))
        for criterion in selected_criteria
    }
    if any(
        not refs or not refs.intersection(submitted_refs)
        for refs in criterion_refs.values()
    ):
        return None

    claims: list[_RenderedClaim] = []
    seen: set[tuple[str | None, tuple[str, ...], ClaimPlacement, str]] = set()

    def add_claim(
        criterion_key: str | None,
        refs: tuple[str, ...],
        placement: ClaimPlacement,
        descriptor: str,
    ) -> None:
        if not refs or not descriptor:
            return
        identity = (criterion_key, refs, placement, descriptor)
        if identity in seen:
            return
        seen.add(identity)
        claims.append(
            _RenderedClaim(
                criterion_key=criterion_key,
                evidence_refs=refs,
                placement=placement,
                descriptor=descriptor,
                rendered=_render_claim(placement, descriptor),
            )
        )

    for default_placement, packets in (
        ("match", context.reasons),
        ("tradeoff", context.tradeoffs),
        ("unknown", context.unknowns),
    ):
        for packet in packets:
            packet_refs = tuple(
                ref for ref in _packet_refs(packet) if ref in submitted_refs
            )
            packet_placement = packet.get("placement", default_placement)
            if packet_placement not in {"match", "tradeoff", "unknown"}:
                return None
            packet_claim_placement = cast(ClaimPlacement, packet_placement)
            packet_key = packet.get("criterion_key")
            if isinstance(packet_key, str):
                candidate_keys: tuple[str, ...] = (
                    (packet_key,) if packet_key in selected_criteria else ()
                )
            else:
                candidate_keys = tuple(
                    criterion
                    for criterion in selected_criteria
                    if set(packet_refs).intersection(criterion_refs[criterion])
                )
            descriptor = packet.get("fact")
            if not isinstance(descriptor, str):
                descriptor = packet.get("label")
            if not isinstance(descriptor, str):
                continue
            for criterion in candidate_keys:
                refs = tuple(
                    ref for ref in packet_refs if ref in criterion_refs[criterion]
                )
                add_claim(criterion, refs, packet_claim_placement, descriptor)

    for fact in context.geography:
        if fact.source_ref not in submitted_refs:
            continue
        candidate_keys = (
            (fact.criterion_key,)
            if fact.criterion_key in selected_criteria
            else tuple(
                criterion
                for criterion in selected_criteria
                if fact.source_ref in criterion_refs[criterion]
            )
        )
        fact_placement: ClaimPlacement = (
            "match" if fact.favorable else "tradeoff"
        )
        for criterion in candidate_keys:
            if criterion is None:
                continue
            if fact.source_ref in criterion_refs[criterion]:
                add_claim(
                    criterion,
                    (fact.source_ref,),
                    fact_placement,
                    fact.value,
                )

    if "listing_field:price" in submitted_refs:
        for change in context.price_changes:
            rendered = _render_price_change(change)
            if rendered is not None:
                claims.append(
                    _RenderedClaim(
                        criterion_key=None,
                        evidence_refs=("listing_field:price",),
                        placement="price",
                        descriptor=rendered,
                        rendered=rendered,
                    )
                )
                break

    claimed_criteria = {
        claim.criterion_key for claim in claims if claim.criterion_key is not None
    }
    claimed_refs = {
        ref for claim in claims for ref in claim.evidence_refs
    }
    if claimed_criteria != set(selected_criteria):
        return None
    if claimed_refs != set(submitted_refs):
        return None
    return tuple(claims)


def _render_claim(
    placement: ClaimPlacement,
    descriptor: str,
) -> str:
    if placement == "match":
        return f"Encaja por {_with_article(_match_descriptor(descriptor))}."
    if placement == "tradeoff":
        return f"{_capitalize(_with_article(descriptor))} es un punto para revisar."
    if placement == "unknown":
        return f"No puedo confirmar {descriptor}."
    return descriptor


def _render_price_change(change: Mapping[str, object]) -> str | None:
    before = change.get("before")
    after = change.get("after")
    currency = change.get("currency")
    if not isinstance(before, (int, float)) or isinstance(before, bool):
        return None
    if not isinstance(after, (int, float)) or isinstance(after, bool):
        return None
    if not isinstance(currency, str) or before == after:
        return None
    before_text = f"{before:,.0f}".replace(",", ".")
    after_text = f"{after:,.0f}".replace(",", ".")
    if after < before:
        return f"Bajó de {currency} {before_text} a {currency} {after_text}."
    return f"El precio pasó de {currency} {before_text} a {currency} {after_text}."


def _with_article(descriptor: str) -> str:
    article = {
        "buena conectividad": "la",
        "superficie": "la",
    }.get(descriptor.casefold())
    return f"{article} {descriptor}" if article else descriptor


def _match_descriptor(descriptor: str) -> str:
    return descriptor[4:] if descriptor.casefold().startswith("con ") else descriptor


def _capitalize(value: str) -> str:
    return value[:1].upper() + value[1:]


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
