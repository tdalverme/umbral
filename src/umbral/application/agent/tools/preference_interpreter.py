"""LLM-based preference interpretation with versioned structured bindings.

The model only fills the structured ``preference-interpret-v1`` payload: given
a natural phrase and the published concept catalog it either resolves a
canonical concept (``structured``) or declares itself unable to (``unresolved``).
It never invents concepts, and the caller keeps the durable expression either
way (FR-010): a phrase with no evaluable concept is preserved as ``unresolved``
instead of being rejected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from umbral.application.agent.ports import ModelGateway


class PreferenceInterpretationError(ValueError):
    """Raised only on structural contract violations, never on unresolved."""


@dataclass(frozen=True, slots=True)
class PreferenceInterpretation:
    """One versioned interpretation of a natural phrase toward the catalog.

    ``kind`` is ``structured`` when a canonical concept was resolved (and then
    ``concept_key``/``polarity``/``value``/``confidence``/``matcher_type`` are
    set), or ``unresolved`` when the phrase has no evaluable canonical concept
    (``reason`` explains the limitation).
    """

    kind: str
    concept_key: str | None = None
    polarity: str | None = None
    value: str | None = None
    confidence: float = 0.0
    matcher_type: str | None = None
    params: Mapping[str, object] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ConceptOption:
    """One published concept the interpreter may resolve to."""

    key: str
    description: str
    matchers: tuple[str, ...]


def resolve_concept(
    *,
    phrase: str,
    concepts: Sequence[ConceptOption],
    gateway: ModelGateway,
    prompt_version: str,
    model_version: str,
    schema_version: str = "preference-interpret-v1",
) -> PreferenceInterpretation | None:
    """Return a structured interpretation, or None on gateway failure.

    Failing the gateway / validation never raises here: the caller treats it
    as an unresolved phrase (kept durably), which is the safe default.
    """
    catalog = [
        {
            "key": concept.key,
            "description": concept.description,
            "matchers": list(concept.matchers),
        }
        for concept in concepts
    ]
    schema: dict[str, object] = {
        "resolution": "string",
        "reason": "string",
        "concept_key": "string",
        "polarity": "string",
        "value": "string",
        "confidence": "number",
        "matcher_type": "string",
        "params": {
            "kind": "list",
            "item": {"key": "string", "value": "string"},
        },
    }
    prompt_schema = dict(schema)
    prompt_schema["_catalog"] = catalog
    prompt_schema["_instructions"] = (
        "Dado el mensaje del usuario, elige UNA resolucion:\n"
        "- 'structured': la frase expresa una preferencia clara sobre UN "
        "concepto del catalogo. Rellena concept_key (exacto del catalogo), "
        "polarity (positive/negative), value opcional, confidence 0..1, "
        "matcher_type (uno de los matchers validos del concepto) y params "
        "con el valor.\n"
        "- 'unresolved': la frase NO corresponde a ningun concepto del "
        "catalogo (o es vaga, o pide algo no evaluable). Rellena reason "
        "explicando la limitacion y deja concept_key vacio.\n"
        "Nunca inventes concept_key fuera del catalogo ni fuerces una "
        "preferencia que no este explicitamente pedida."
    )
    result = gateway.generate_structured(
        messages=({"role": "user", "content": phrase},),
        schema=prompt_schema,
        schema_version=schema_version,
        prompt_version=prompt_version,
        model_version=model_version,
    )
    if result.status != "success" or result.content is None:
        return None
    return _interpretation_from_data(result.content, catalog)


def _interpretation_from_data(
    data: Mapping[str, object], catalog: Sequence[Mapping[str, object]]
) -> PreferenceInterpretation | None:
    resolution = data.get("resolution")
    if resolution == "unresolved":
        return PreferenceInterpretation(
            kind="unresolved",
            reason=str(data.get("reason") or "no evaluable"),
        )
    if resolution != "structured":
        return None
    concept_key = data.get("concept_key")
    if not isinstance(concept_key, str) or not concept_key:
        return PreferenceInterpretation(
            kind="unresolved", reason="structured sin concept_key"
        )
    concept = next((c for c in catalog if c.get("key") == concept_key), None)
    if concept is None:
        return PreferenceInterpretation(
            kind="unresolved", reason=f"concepto {concept_key} no publicado"
        )
    valid_matchers = concept.get("matchers")
    matcher_set = (
        frozenset(str(item) for item in valid_matchers)
        if isinstance(valid_matchers, (list, tuple))
        else frozenset()
    )
    matcher_type = data.get("matcher_type")
    if matcher_type is not None and matcher_type not in matcher_set:
        return PreferenceInterpretation(
            kind="unresolved",
            reason=f"matcher {matcher_type} no valido para {concept_key}",
        )
    polarity = data.get("polarity")
    if not isinstance(polarity, str) or polarity not in {"positive", "negative"}:
        return PreferenceInterpretation(
            kind="unresolved", reason="polarity invalida"
        )
    value = data.get("value")
    value_str = value if isinstance(value, str) and value else None
    raw_params = data.get("params")
    params_items = raw_params if isinstance(raw_params, list) else []
    return PreferenceInterpretation(
        kind="structured",
        concept_key=concept_key,
        polarity=polarity,
        value=value_str,
        confidence=_clamp01(_number(data.get("confidence"), 0.6)),
        matcher_type=matcher_type if isinstance(matcher_type, str) else None,
        params={
            str(item.get("key")): str(item.get("value"))
            for item in params_items
            if isinstance(item, Mapping) and "key" in item and "value" in item
        },
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _number(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default
