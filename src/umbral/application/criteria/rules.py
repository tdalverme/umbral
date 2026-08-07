"""Deterministic objective extraction rules with fragment evidence.

Each rule is a pure function over the permitted projection of a normalized
listing. It returns a :class:`RuleOutcome` with the observed value and the
exact fragment evidence; when no signal is matchable the value is ``None``
and the outcome declares "sin evidencia" explicitly instead of inventing one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from umbral.application.criteria.contracts import RuleOutcome

_BALCON_POSITIVE = re.compile(r"\bbalc[oó]n\b", re.IGNORECASE)
_BALCON_NEGATIVE = re.compile(
    r"\bsin\s+balc[oó]n\b|\bno\s+(?:tiene|tiene)?\s*balc[oó]n\b", re.IGNORECASE
)
_AMBIENTES = re.compile(r"(\d{1,2})\s*ambientes?\b", re.IGNORECASE)
_PISO = re.compile(
    r"\bpiso\s+(\d{1,3})\b|\b(\d{1,3})[º°]\s*(?:piso|planta)\b", re.IGNORECASE
)
_COCINA_SEPARADA = re.compile(r"cocina\s+separada", re.IGNORECASE)
_COCINA_INTEGRADA = re.compile(r"cocina\s+integrada|\bintegrada\b", re.IGNORECASE)
_COCINA_NONE = re.compile(
    r"\bsin\s+cocina\b|\bno\s+tiene\s+cocina\b|\bsin\s+espacio\s+para\s+cocina\b",
    re.IGNORECASE,
)


def _match(regex: re.Pattern[str], text: str) -> re.Match[str] | None:
    return regex.search(text)


def _fragment(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 24)
    end = min(len(text), match.end() + 24)
    return text[start:end].strip()


def run_balcon(projection: Mapping[str, object]) -> RuleOutcome:
    text = str(projection.get("description_text") or "")
    negative = _match(_BALCON_NEGATIVE, text)
    if negative:
        return RuleOutcome(
            "false",
            _fragment(text, negative),
            (negative.start(), negative.end()),
            ("description_text",),
        )
    positive = _match(_BALCON_POSITIVE, text)
    if positive:
        return RuleOutcome(
            "true",
            _fragment(text, positive),
            (positive.start(), positive.end()),
            ("description_text",),
        )
    amenities = projection.get("amenities")
    if isinstance(amenities, list):
        for amenity in amenities:
            if _BALCON_POSITIVE.search(str(amenity)):
                return RuleOutcome("true", str(amenity), None, ("amenities",))
    return RuleOutcome(None, None, None)


def run_ambientes(projection: Mapping[str, object]) -> RuleOutcome:
    text = str(projection.get("description_text") or "")
    match = _match(_AMBIENTES, text)
    if match:
        return RuleOutcome(
            int(match.group(1)),
            _fragment(text, match),
            (match.start(), match.end()),
            ("description_text",),
        )
    rooms = projection.get("rooms")
    if isinstance(rooms, int):
        return RuleOutcome(rooms, None, None)
    return RuleOutcome(None, None, None)


def run_piso(projection: Mapping[str, object]) -> RuleOutcome:
    text = str(projection.get("description_text") or "")
    match = _match(_PISO, text)
    if match:
        value = match.group(1) or match.group(2)
        return RuleOutcome(
            int(value),
            _fragment(text, match),
            (match.start(), match.end()),
            ("description_text",),
        )
    floor = projection.get("floor")
    if isinstance(floor, int):
        return RuleOutcome(floor, None, None)
    return RuleOutcome(None, None, None)


def run_tipo_cocina(projection: Mapping[str, object]) -> RuleOutcome:
    text = str(projection.get("description_text") or "")
    none_match = _COCINA_NONE.search(text)
    if none_match:
        return RuleOutcome(
            "none",
            _fragment(text, none_match),
            (none_match.start(), none_match.end()),
            ("description_text",),
        )
    separate_match = _COCINA_SEPARADA.search(text)
    if separate_match:
        return RuleOutcome(
            "separada",
            _fragment(text, separate_match),
            (separate_match.start(), separate_match.end()),
            ("description_text",),
        )
    integrated_match = _COCINA_INTEGRADA.search(text)
    if integrated_match:
        return RuleOutcome(
            "integrada",
            _fragment(text, integrated_match),
            (integrated_match.start(), integrated_match.end()),
            ("description_text",),
        )
    return RuleOutcome(None, None, None)


RULE_RUNNERS = {
    "balcon": run_balcon,
    "ambientes": run_ambientes,
    "piso": run_piso,
    "tipo_cocina": run_tipo_cocina,
}


def run_rule(concept_key: str, projection: Mapping[str, object]) -> RuleOutcome:
    """Run the deterministic rule registered for ``concept_key``."""

    runner = RULE_RUNNERS.get(concept_key)
    if runner is None:
        raise KeyError(f"no rule registered for concept: {concept_key}")
    return runner(projection)


def rule_version(concept_key: str) -> str:
    """Immutable version identifier of the rule implementation."""

    return f"{concept_key}.rule-v1"
