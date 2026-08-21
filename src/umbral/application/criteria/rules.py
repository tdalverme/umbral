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
_DORMITORIOS = re.compile(
    r"(\d{1,2})\s*dormitorios?\b|\b(\d{1,2})\s*habitaciones?\b|\b(\d{1,2})\s*cuartos?\b",
    re.IGNORECASE,
)
_MASCOTAS_POSITIVE = re.compile(
    r"\b(?:aceptan|acepta|admiten|admite|permiten|permite|se aceptan|se admiten|"
    r"se permiten)\s*mascotas\b|\bpet\s+friendly\b|\bcon\s+mascotas\b",
    re.IGNORECASE,
)
_MASCOTAS_NEGATIVE = re.compile(
    r"\b(?:no aceptan|no acepta|no admiten|no admite|no permiten|no permite)"
    r"\s*mascotas\b|\b(?:sin mascotas|no se aceptan mascotas|no se admiten"
    r"\s*mascotas|no se reciben mascotas)\b",
    re.IGNORECASE,
)
_ASCENSOR = re.compile(r"\bascensor(?:es)?\b|\belevador(?:es)?\b", re.IGNORECASE)
_COCHERA = re.compile(
    r"\bcochera\b|\bgarage\b|\bgaraje\b|\bparking\b|\bstacionamiento\b", re.IGNORECASE
)
_PISCINA = re.compile(r"\bpiscina\b|\bpileta\b", re.IGNORECASE)
_NO_ASCENSOR = re.compile(
    r"\bsin\s+ascensor\b|\bno\s+tiene\s+ascensor\b", re.IGNORECASE
)
_NO_COCHERA = re.compile(
    r"\bsin\s+cochera\b|\bsin\s+garage\b|\bno\s+tiene\s+cochera\b", re.IGNORECASE
)
_NO_PISCINA = re.compile(
    r"\bsin\s+piscina\b|\bsin\s+pileta\b|\bno\s+tiene\s+piscina\b", re.IGNORECASE
)
_CON_ASCENSOR = re.compile(
    r"\bcon\s+ascensor\b|\btiene\s+ascensor\b", re.IGNORECASE
)
_CON_COCHERA = re.compile(
    r"\bcon\s+cochera\b|\btiene\s+cochera\b", re.IGNORECASE
)
_CON_PISCINA = re.compile(
    r"\bcon\s+piscina\b|\bcon\s+pileta\b|\btiene\s+piscina\b", re.IGNORECASE
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


def run_dormitorios(projection: Mapping[str, object]) -> RuleOutcome:
    """Deterministic bedrooms extraction: the structured ``bedrooms`` field of
    the NormalizedListing wins; falling back to free text keeps evidence only
    when the phrasing declares a count."""
    bedrooms = projection.get("bedrooms")
    if isinstance(bedrooms, int):
        return RuleOutcome(bedrooms, None, None)
    text = str(projection.get("description_text") or "")
    match = _DORMITORIOS.search(text)
    if match:
        value = next(group for group in match.groups() if group is not None)
        return RuleOutcome(
            int(value),
            _fragment(text, match),
            (match.start(), match.end()),
            ("description_text",),
        )
    return RuleOutcome(None, None, None)


def run_mascotas(projection: Mapping[str, object]) -> RuleOutcome:
    """Pets allowed detection: adjective-free positive/negative wording over
    description and amenities; ambiguous text stays unknown instead of
    inventing a value (FR-003)."""
    text = str(projection.get("description_text") or "")
    amenities = projection.get("amenities")
    amenities_text = (
        " ".join(str(item) for item in amenities)
        if isinstance(amenities, list)
        else ""
    )

    negative_text = _MASCOTAS_NEGATIVE.search(text)
    if negative_text:
        return RuleOutcome(
            "false",
            _fragment(text, negative_text),
            (negative_text.start(), negative_text.end()),
            ("description_text",),
        )
    negative_amenity = _MASCOTAS_NEGATIVE.search(amenities_text)
    if negative_amenity:
        return RuleOutcome(
            "false",
            _fragment(amenities_text, negative_amenity),
            (negative_amenity.start(), negative_amenity.end()),
            ("amenities",),
        )
    positive_text = _MASCOTAS_POSITIVE.search(text)
    if positive_text:
        return RuleOutcome(
            "true",
            _fragment(text, positive_text),
            (positive_text.start(), positive_text.end()),
            ("description_text",),
        )
    positive_amenity = _MASCOTAS_POSITIVE.search(amenities_text)
    if positive_amenity:
        return RuleOutcome(
            "true",
            _fragment(amenities_text, positive_amenity),
            (positive_amenity.start(), positive_amenity.end()),
            ("amenities",),
        )
    return RuleOutcome(None, None, None)


def _boolean_amenity_rule(
    *,
    positive: re.Pattern[str],
    negative: re.Pattern[str],
    declarative: re.Pattern[str],
    projection: Mapping[str, object],
) -> RuleOutcome:
    """Shared deterministic boolean-amenity rule: amenities list wins with the
    amenity as evidence; description only declares ``true`` with explicit
    declarative wording (``con``/``tiene``) and ``false`` with an explicit
    negative. A bare mention never confirms, so free-text like "sin informacion
    de ascensor" stays unknown instead of a false positive."""
    amenities = projection.get("amenities")
    if isinstance(amenities, list):
        for amenity in amenities:
            if positive.search(str(amenity)):
                return RuleOutcome("true", str(amenity), None, ("amenities",))
            if negative.search(str(amenity)):
                return RuleOutcome("false", str(amenity), None, ("amenities",))
    text = str(projection.get("description_text") or "")
    neg = negative.search(text)
    if neg:
        return RuleOutcome(
            "false",
            _fragment(text, neg),
            (neg.start(), neg.end()),
            ("description_text",),
        )
    pos = declarative.search(text)
    if pos:
        return RuleOutcome(
            "true",
            _fragment(text, pos),
            (pos.start(), pos.end()),
            ("description_text",),
        )
    return RuleOutcome(None, None, None)


def run_ascensor(projection: Mapping[str, object]) -> RuleOutcome:
    return _boolean_amenity_rule(
        positive=_ASCENSOR,
        negative=_NO_ASCENSOR,
        declarative=_CON_ASCENSOR,
        projection=projection,
    )


def run_cochera(projection: Mapping[str, object]) -> RuleOutcome:
    parking_spaces = projection.get("parking_spaces")
    if (
        isinstance(parking_spaces, (int, float))
        and not isinstance(parking_spaces, bool)
        and parking_spaces >= 0
    ):
        value = "true" if parking_spaces > 0 else "false"
        return RuleOutcome(
            value,
            f"parking_spaces={parking_spaces:g}",
            None,
            ("parking_spaces",),
        )
    return _boolean_amenity_rule(
        positive=_COCHERA,
        negative=_NO_COCHERA,
        declarative=_CON_COCHERA,
        projection=projection,
    )


def run_piscina(projection: Mapping[str, object]) -> RuleOutcome:
    return _boolean_amenity_rule(
        positive=_PISCINA,
        negative=_NO_PISCINA,
        declarative=_CON_PISCINA,
        projection=projection,
    )


def run_precio_m2(projection: Mapping[str, object]) -> RuleOutcome:
    """Deterministic price-per-area from the normalized price and surface.

    The price keeps its declared currency (no unversioned conversion); without
    a surface or with a non-positive price the outcome is unknown and never
    invents a value (FR-008).
    """
    price = projection.get("price_value")
    surface = projection.get("surface_m2")
    if (
        isinstance(price, bool)
        or not isinstance(price, (int, float))
        or isinstance(surface, bool)
        or not isinstance(surface, (int, float))
        or price <= 0
        or surface <= 0
    ):
        return RuleOutcome(None, None, None)
    currency = str(projection.get("price_currency") or "ARS")
    value = round(float(price) / float(surface), 2)
    fragment = f"precio {price} {currency} / superficie {surface:.1f} m2"
    return RuleOutcome(value, fragment, None, ("price_value", "surface_m2"))


def run_variacion_precio(projection: Mapping[str, object]) -> RuleOutcome:
    """Deterministic price-change signal from the listing's price history.

    Reads the most recent ``price`` change row of the listing (the reader
    orders by created_at desc). Value = after - before, so a drop is negative
    and a rise positive. No prior price change is unknown, never an implicit
    "sin cambio" (FR-009).
    """
    changes = projection.get("price_changes")
    if not isinstance(changes, list):
        return RuleOutcome(None, None, None)
    for raw in changes:
        if not isinstance(raw, Mapping):
            continue
        field = str(raw.get("field") or "")
        if field and field not in {"price_value", "total_cost", "expenses_value"}:
            continue
        before = raw.get("before")
        after = raw.get("after")
        if (
            isinstance(before, bool)
            or not isinstance(before, (int, float))
            or isinstance(after, bool)
            or not isinstance(after, (int, float))
        ):
            continue
        delta = round(float(after) - float(before), 2)
        fragment = f"precio {before} -> {after}"
        return RuleOutcome(delta, fragment, None, ("price_changes",))
    return RuleOutcome(None, None, None)


RULE_RUNNERS = {
    "balcon": run_balcon,
    "ambientes": run_ambientes,
    "piso": run_piso,
    "tipo_cocina": run_tipo_cocina,
    "dormitorios": run_dormitorios,
    "mascotas": run_mascotas,
    "ascensor": run_ascensor,
    "cochera": run_cochera,
    "piscina": run_piscina,
    "precio_m2": run_precio_m2,
    "variacion_precio": run_variacion_precio,
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
