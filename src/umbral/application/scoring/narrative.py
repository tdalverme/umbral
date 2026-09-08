"""Pure, bounded inputs for grounded opportunity narratives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from umbral.application.criteria.contracts import ListingObservation
from umbral.application.scoring.contracts import (
    Explanation,
    ExplanationNarrativeContext,
    ExplanationReason,
    ExplanationRisk,
    GeographicFact,
)

_SAFE_LISTING_FIELDS = {
    "price_value": "price",
    "surface_m2": "surface_m2",
    "rooms": "rooms",
    "expenses_value": "expenses",
    "neighborhood": "neighborhood",
}

_DEFAULT_LABELS = {
    "acceso_transporte": "buena conectividad",
    "proximidad_cafes": "cafés cercanos",
    "proximidad_parque": "espacios verdes cerca",
    "proximidad_compras": "servicios cotidianos cerca",
    "vida_nocturna": "actividad nocturna",
    "calma_residencial": "entorno más residencial",
    "ruido_transito": "menor exposición",
    "ruido_ambiental": "menor exposición",
}

_GEOGRAPHIC_SIGNAL_ORDER = (
    "road_noise",
    "transit_access",
    "green_access",
    "daily_convenience",
    "cafe_lifestyle",
    "commercial_intensity",
    "nightlife_intensity",
    "residential_calm",
    "noise_risk",
)


def select_material_evaluations(
    explanation: Explanation,
    active_criteria: Mapping[str, object],
) -> Sequence[ExplanationReason | ExplanationRisk]:
    """Keep the highest-impact active matches and only active caveats."""

    reasons = [
        reason
        for reason in explanation.reasons
        if reason.criterion_key in active_criteria
    ][:4]
    risks = [
        risk
        for risk in explanation.risks
        if risk.criterion_key in active_criteria
    ][:2]
    return tuple(reasons + risks)


def geographic_facts(
    observations: Mapping[str, ListingObservation],
) -> Sequence[GeographicFact]:
    """Translate retained urban measurements to bounded, proxy-safe facts."""

    by_signal: dict[str, ListingObservation] = {}
    for observation in observations.values():
        if observation.source != "urban" or observation.state != "active":
            continue
        signal_ref = observation.evidence.get("signal_ref")
        if isinstance(signal_ref, str):
            by_signal.setdefault(signal_ref, observation)

    facts: list[GeographicFact] = []
    for signal_ref in _GEOGRAPHIC_SIGNAL_ORDER:
        observation = by_signal.get(signal_ref)
        if observation is None:
            continue
        fact = _geographic_fact(observation, signal_ref)
        if fact is not None:
            facts.append(fact)
    return tuple(facts)


def build_narrative_context(
    *,
    explanation: Explanation,
    listing: Mapping[str, object],
    active_criteria: Mapping[str, object],
    observations: Mapping[str, ListingObservation],
    price_changes: Sequence[Mapping[str, object]] = (),
) -> ExplanationNarrativeContext:
    """Project deterministic evidence into the minimal narrative packet."""

    material = select_material_evaluations(explanation, active_criteria)
    material_keys = {item.criterion_key for item in material}
    reasons = tuple(
        _evaluation_packet(reason, active_criteria)
        for reason in material
        if isinstance(reason, ExplanationReason) and reason.state == "match"
    )
    tradeoffs = tuple(
        _evaluation_packet(reason, active_criteria)
        for reason in material
        if isinstance(reason, ExplanationReason) and reason.state == "mismatch"
    )
    unknowns = tuple(
        _risk_packet(risk, active_criteria)
        for risk in material
        if isinstance(risk, ExplanationRisk) and risk.state == "unknown"
    )
    geography = tuple(
        fact
        for key, observation in observations.items()
        if key in material_keys
        for fact in geographic_facts({key: observation})
    )
    allowed_evidence_refs = tuple(
        sorted(
            {
                ref
                for packet in reasons + tradeoffs + unknowns
                for ref in packet["evidence_refs"]
                if isinstance(ref, str)
            }
            | {fact.source_ref for fact in geography}
        )
    )
    return ExplanationNarrativeContext(
        listing={
            destination: listing[source]
            for source, destination in _SAFE_LISTING_FIELDS.items()
            if listing.get(source) is not None
        },
        active_priorities=tuple(
            _priority_packet(key, value) for key, value in active_criteria.items()
        ),
        reasons=reasons,
        tradeoffs=tradeoffs,
        unknowns=unknowns,
        geography=geography,
        price_changes=tuple(_price_change(change) for change in price_changes),
        allowed_criteria=tuple(active_criteria),
        allowed_evidence_refs=allowed_evidence_refs,
    )


def _geographic_fact(
    observation: ListingObservation, signal_ref: str) -> GeographicFact | None:
    composite_fact = _composite_fact(signal_ref, observation.value)
    if composite_fact is not None:
        label, value = composite_fact
        return GeographicFact(
            label=label,
            value=value,
            source_ref=f"urban:{observation.observation_id}",
            confidence=observation.confidence,
        )
    contributor = _first_factual_contributor(observation)
    if contributor is None:
        return None
    observed_value, unit = contributor
    phrase = _phrase(signal_ref, observed_value, unit)
    if phrase is None:
        return None
    return GeographicFact(
        label=_DEFAULT_LABELS.get(observation.concept_key, "entorno"),
        value=phrase,
        source_ref=f"urban:{observation.observation_id}",
        confidence=observation.confidence,
    )


def _first_factual_contributor(
    observation: ListingObservation,
) -> tuple[float | int, str] | None:
    contributors = observation.evidence.get("contributors")
    if not isinstance(contributors, list):
        return None
    for contributor in contributors:
        if not isinstance(contributor, Mapping):
            continue
        value = contributor.get("observed_value")
        unit = contributor.get("unit")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(unit, str)
        ):
            return value, unit
    return None


def _composite_fact(signal_ref: str, value: object) -> tuple[str, str] | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if signal_ref == "residential_calm":
        return "entorno más residencial", "entorno más residencial"
    if signal_ref == "noise_risk":
        if value >= 0.5:
            return "mayor actividad", "mayor exposición a actividad urbana"
        return "menor exposición", "menor exposición a actividad urbana"
    return None


def _phrase(signal_ref: str, value: float | int, unit: str) -> str | None:
    if signal_ref == "road_noise" and unit == "m":
        if value >= 300:
            return "alejada de los principales corredores"
        if value >= 120:
            return "sin estar directamente sobre una avenida grande"
        return "con una avenida principal relativamente cerca"
    if signal_ref == "transit_access" and unit == "m":
        return (
            "subte relativamente cerca"
            if value <= 600
            else "con transporte a una distancia mayor"
        )
    if signal_ref == "green_access" and unit == "m":
        return (
            "espacio verde relativamente cerca"
            if value <= 600
            else "espacio verde a una distancia mayor"
        )
    if signal_ref == "daily_convenience" and unit == "places":
        return (
            "varios servicios cotidianos cerca"
            if value >= 3
            else "algunos servicios cotidianos cerca"
        )
    if signal_ref == "cafe_lifestyle" and unit == "places":
        return "varios cafés cerca" if value >= 3 else "algunos cafés cerca"
    if signal_ref == "commercial_intensity" and unit == "places":
        return (
            "mayor actividad comercial"
            if value >= 3
            else "actividad comercial cercana"
        )
    if signal_ref == "nightlife_intensity" and unit == "places":
        return (
            "mayor actividad nocturna"
            if value >= 3
            else "algo de actividad nocturna cerca"
        )
    if signal_ref == "residential_calm":
        return "entorno más residencial"
    if signal_ref == "noise_risk":
        return "menor exposición"
    return None


def _evaluation_packet(
    reason: ExplanationReason,
    active_criteria: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "label": _label(reason.criterion_key, active_criteria),
        "state": reason.state,
        "confidence": reason.confidence,
        "evidence_refs": _evidence_refs(reason.evidence_refs),
    }


def _risk_packet(
    risk: ExplanationRisk,
    active_criteria: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "label": _label(risk.criterion_key, active_criteria),
        "state": risk.state,
        "evidence_refs": (),
    }


def _priority_packet(key: str, value: object) -> Mapping[str, object]:
    details = value if isinstance(value, Mapping) else {}
    return {
        "key": key,
        "label": details.get("label", _DEFAULT_LABELS.get(key, "esta prioridad")),
        "polarity": details.get("polarity", "positive"),
    }


def _evidence_refs(refs: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(
        f"{ref['kind']}:{ref['ref']}"
        for ref in refs
        if isinstance(ref.get("kind"), str) and isinstance(ref.get("ref"), str)
    )


def _label(key: str, active_criteria: Mapping[str, object]) -> str:
    value = active_criteria.get(key)
    if isinstance(value, Mapping) and isinstance(value.get("label"), str):
        return value["label"]
    return _DEFAULT_LABELS.get(key, "esta prioridad")


def _price_change(change: Mapping[str, object]) -> Mapping[str, object]:
    return {
        key: change[key]
        for key in ("field", "before", "after", "currency")
        if key in change
    }
