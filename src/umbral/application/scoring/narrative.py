"""Pure, bounded inputs for grounded opportunity narratives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

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
    "price_currency": "price_currency",
    "surface_m2": "surface_m2",
    "rooms": "rooms",
    "expenses_value": "expenses",
    "neighborhood": "neighborhood",
}

_DEFAULT_LABELS = {
    "presupuesto": "presupuesto",
    "ambientes": "cantidad de ambientes",
    "superficie": "superficie",
    "ubicacion": "ubicación",
    "piso": "piso",
    "tipo_cocina": "tipo de cocina",
    "balcon": "balcón",
    "luminosidad": "buena luz natural",
    "estado_general": "buen estado general",
    "barrio_seguro": "entorno del barrio",
    "moderno": "estilo moderno",
    "dormitorios": "dormitorios",
    "banos": "baños",
    "mascotas": "acepta mascotas",
    "amoblado": "nivel de amoblamiento",
    "ascensor": "ascensor",
    "cochera": "cochera",
    "piscina": "piscina",
    "precio_m2": "precio por metro cuadrado",
    "variacion_precio": "variación del precio",
    "acceso_transporte": "buena conectividad",
    "proximidad_cafes": "cafés cercanos",
    "proximidad_parque": "espacios verdes cerca",
    "proximidad_compras": "servicios cotidianos cerca",
    "vida_nocturna": "actividad nocturna",
    "zona_comercial": "actividad comercial",
    "caminabilidad": "facilidad para moverte a pie",
    "calma_residencial": "entorno más residencial",
    "ruido_transito": "menor exposición",
    "ruido_tren": "menor exposición al tren",
    "ruido_ambiental": "menor exposición",
    "acceso_escuela": "escuelas cerca",
    "acceso_deporte": "espacios para hacer deporte cerca",
    "acceso_cultura": "espacios culturales cerca",
    "acceso_bici": "facilidad para moverte en bici",
    "acceso_salud": "servicios de salud cerca",
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


@dataclass(frozen=True, slots=True)
class ExplanationNarrative:
    """Auditable presentation copy for one already-ranked opportunity."""

    text: str
    used_criteria: tuple[str, ...]
    used_evidence_refs: tuple[str, ...]
    source: Literal["managed", "deterministic_fallback"]
    prompt_version: str
    model_version: str


def deterministic_narrative(
    context: ExplanationNarrativeContext,
    *,
    prompt_version: str = "explanation-narrative-v1",
    model_version: str = "deterministic",
) -> ExplanationNarrative:
    """Describe bounded reasons without model availability or inference."""

    selected_reasons = [
        item for item in context.reasons if _string(item.get("label"))
    ][:3]
    reasons = [
        descriptor
        for item in selected_reasons
        if (
            descriptor := _string(item.get("fact"))
            or _string(item.get("label"))
        )
    ]
    selected_geography = [fact for fact in context.geography if fact.favorable][
        : max(0, 3 - len(reasons))
    ]
    geography = [fact.value for fact in selected_geography]
    matches = [value for value in reasons + geography if value is not None]
    if matches:
        text = f"Encaja por {_join_spanish(matches)}."
    else:
        text = "Encaja con parte de lo que buscás."

    tradeoff_item = next(
        (item for item in context.tradeoffs if _string(item.get("label"))), None
    )
    tradeoff = (
        _string(tradeoff_item.get("fact")) or _string(tradeoff_item.get("label"))
        if tradeoff_item
        else None
    )
    tradeoff_fact = None
    if tradeoff is None:
        tradeoff_fact = next(
            (fact for fact in context.geography if not fact.favorable), None
        )
        tradeoff = tradeoff_fact.value if tradeoff_fact is not None else None
    if tradeoff:
        text += f" {tradeoff[0].upper() + tradeoff[1:]} es un punto para revisar."
    elif context.unknowns:
        unknown = _string(context.unknowns[0].get("label"))
        if unknown:
            text += f" No puedo confirmar {unknown}."

    price_change = next(
        (
            change
            for change in context.price_changes
            if _is_complete_price_change(change, change.get("currency"))
            and change.get("before") != change.get("after")
        ),
        None,
    )
    if price_change is not None:
        before = price_change["before"]
        after = price_change["after"]
        currency = price_change["currency"]
        assert isinstance(before, (int, float)) and not isinstance(before, bool)
        assert isinstance(after, (int, float)) and not isinstance(after, bool)
        assert isinstance(currency, str)
        if after < before:
            text += (
                f" Bajó de {_price_text(before, currency)}"
                f" a {_price_text(after, currency)}."
            )
        elif after > before:
            text += (
                f" El precio pasó de {_price_text(before, currency)}"
                f" a {_price_text(after, currency)}."
            )
    used_criteria: tuple[str, ...] = tuple(
        key
        for item in selected_reasons
        if (key := item.get("criterion_key")) is not None
        and isinstance(key, str)
    ) + tuple(
        fact.criterion_key
        for fact in selected_geography
        if fact.favorable and fact.criterion_key
    )
    if tradeoff_item is not None and isinstance(
        tradeoff_item.get("criterion_key"), str
    ):
        tradeoff_key = tradeoff_item.get("criterion_key")
        assert isinstance(tradeoff_key, str)
        used_criteria += (tradeoff_key,)
    used_evidence_refs = tuple(
        ref for item in selected_reasons for ref in _packet_evidence_refs(item)
    ) + tuple(fact.source_ref for fact in selected_geography) + tuple(
        ref for ref in _packet_evidence_refs(tradeoff_item)
    )
    if tradeoff_fact is not None:
        used_evidence_refs += (tradeoff_fact.source_ref,)
        if tradeoff_fact.criterion_key:
            used_criteria += (tradeoff_fact.criterion_key,)
    if tradeoff_item is None and tradeoff_fact is None and context.unknowns:
        unknown_item = next(
            (item for item in context.unknowns if _string(item.get("label"))), None
        )
        if unknown_item is not None and isinstance(
            unknown_item.get("criterion_key"), str
        ):
            unknown_key = unknown_item.get("criterion_key")
            assert isinstance(unknown_key, str)
            used_criteria += (unknown_key,)
    used_criteria = _unique_strings(used_criteria)
    if price_change is not None:
        used_evidence_refs += ("listing_field:price",)
    used_evidence_refs = _unique_strings(used_evidence_refs)
    return ExplanationNarrative(
        text=text,
        used_criteria=used_criteria,
        used_evidence_refs=used_evidence_refs,
        source="deterministic_fallback",
        prompt_version=prompt_version,
        model_version=model_version,
    )


def select_material_evaluations(
    explanation: Explanation,
    active_criteria: Mapping[str, object],
) -> Sequence[ExplanationReason | ExplanationRisk]:
    """Keep the highest-impact active matches and only active caveats."""

    reasons = [
        reason
        for reason in explanation.reasons
        if reason.criterion_key in active_criteria and reason.state == "match"
    ][:4]
    tradeoffs = [
        reason
        for reason in explanation.reasons
        if reason.criterion_key in active_criteria and reason.state == "mismatch"
    ][:2]
    risks = [
        risk
        for risk in explanation.risks
        if risk.criterion_key in active_criteria
    ][:2]
    selected: list[ExplanationReason | ExplanationRisk] = []
    selected.extend(reasons)
    selected.extend(tradeoffs)
    selected.extend(risks)
    return tuple(selected)


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
        candidate_observation = by_signal.get(signal_ref)
        if candidate_observation is None:
            continue
        fact = _geographic_fact(candidate_observation, signal_ref)
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
        _evaluation_packet(reason, active_criteria, observations)
        for reason in material
        if isinstance(reason, ExplanationReason) and reason.state == "match"
    )
    tradeoffs = tuple(
        _evaluation_packet(reason, active_criteria, observations)
        for reason in material
        if isinstance(reason, ExplanationReason) and reason.state == "mismatch"
    )
    unknowns = tuple(
        _risk_packet(risk, active_criteria)
        for risk in material
        if isinstance(risk, ExplanationRisk) and risk.state == "unknown"
    )
    evidence_by_criterion = {
        item.criterion_key: (
            _evidence_refs(item.evidence_refs)
            if isinstance(item, ExplanationReason)
            else ()
        )
        for item in material
    }
    geography_pairs = tuple(
        (key, fact)
        for key, observation in observations.items()
        if key in material_keys
        for fact in geographic_facts({key: observation})
    )
    for key, fact in geography_pairs:
        evidence_by_criterion[key] = tuple(
            sorted({*evidence_by_criterion.get(key, ()), fact.source_ref})
        )
    classified_geography = tuple(
        replace(
            fact,
            favorable=_geography_favorable(key, fact, active_criteria),
        )
        for key, fact in geography_pairs
    )
    geography = tuple(fact for fact in classified_geography if fact.favorable)
    unfavorable = tuple(fact for fact in classified_geography if not fact.favorable)
    unfavorable_keys = {
        fact.criterion_key for fact in unfavorable if fact.criterion_key is not None
    }
    reasons = tuple(
        reason
        for reason in reasons
        if reason.get("criterion_key") not in unfavorable_keys
    )
    tradeoffs = tradeoffs + tuple(
        {
            "criterion_key": fact.criterion_key,
            "label": fact.label,
            "fact": fact.value,
            "state": "mismatch",
            "placement": "tradeoff",
            "evidence_refs": (fact.source_ref,),
        }
        for fact in unfavorable
    )
    packets = (*reasons, *tradeoffs, *unknowns)
    allowed_evidence_refs = tuple(
        sorted(
            {
                ref
                for packet in packets
                for ref in _packet_evidence_refs(packet)
            }
            | {fact.source_ref for fact in geography}
            | (
                {"listing_field:price"}
                if any(
                    _price_change(change, listing.get("price_currency")) is not None
                    for change in price_changes
                )
                else set()
            )
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
        price_changes=tuple(
            projected
            for change in price_changes
            if (
                projected := _price_change(
                    change,
                    listing.get("price_currency"),
                )
            )
            is not None
        ),
        allowed_criteria=tuple(active_criteria),
        allowed_evidence_refs=allowed_evidence_refs,
        criterion_evidence_refs=evidence_by_criterion,
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
            criterion_key=observation.concept_key,
            signal_ref=signal_ref,
            observed_value=observation.value
            if isinstance(observation.value, (int, float))
            and not isinstance(observation.value, bool)
            else None,
            signal_positive=_composite_signal_positive(signal_ref, observation.value),
        )
    contributor = _first_factual_contributor(observation, signal_ref)
    if contributor is None:
        return None
    observed_value, unit, term = contributor
    phrase = _phrase(signal_ref, observed_value, unit, term)
    if phrase is None:
        return None
    return GeographicFact(
        label=_DEFAULT_LABELS.get(observation.concept_key, "entorno"),
        value=phrase,
        source_ref=f"urban:{observation.observation_id}",
        confidence=observation.confidence,
        criterion_key=observation.concept_key,
        signal_ref=signal_ref,
        observed_value=observed_value,
        unit=unit,
        signal_positive=_signal_value_positive(signal_ref, observed_value, unit),
    )


def _geography_favorable(
    key: str, fact: GeographicFact, active_criteria: Mapping[str, object]
) -> bool:
    priority = active_criteria.get(key)
    polarity = priority.get("polarity") if isinstance(priority, Mapping) else "positive"
    positive_signal = _geographic_signal_positive(fact)
    if positive_signal is None:
        return False
    return positive_signal if polarity != "negative" else not positive_signal


def _geographic_signal_positive(fact: GeographicFact) -> bool | None:
    if fact.signal_positive is not None:
        return fact.signal_positive
    if fact.signal_ref in {
        "transit_access",
        "green_access",
        "daily_convenience",
        "cafe_lifestyle",
        "commercial_intensity",
        "nightlife_intensity",
    }:
        return True
    if fact.signal_ref == "residential_calm":
        return fact.value == "entorno más residencial"
    if fact.signal_ref == "noise_risk":
        return fact.value == "mayor exposición a actividad urbana"
    if fact.signal_ref == "road_noise":
        return fact.value == "con una avenida principal relativamente cerca"
    return None


def _first_factual_contributor(
    observation: ListingObservation, signal_ref: str,
) -> tuple[float | int, str, str] | None:
    contributors = observation.evidence.get("contributors")
    if not isinstance(contributors, list):
        return None
    for contributor in contributors:
        if not isinstance(contributor, Mapping):
            continue
        value = contributor.get("observed_value")
        unit = contributor.get("unit")
        term = contributor.get("term")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(unit, str)
            and isinstance(term, str)
            and _term_matches_signal(term, signal_ref)
        ):
            if unit == "places" and value <= 0:
                continue
            phrase = _phrase(signal_ref, value, unit, term)
            if phrase is not None:
                return value, unit, term
    return None


def _term_matches_signal(term: str, signal_ref: str) -> bool:
    expected = {
        "transit_access": (
            "bus_stop.",
            "subway_station.",
            "train_station.",
            "rail_station.",
        ),
        "road_noise": ("major_road.",),
        "green_access": ("green_space.",),
        "daily_convenience": (
            "supermarket.",
            "pharmacy.",
            "convenience.",
            "health.",
        ),
        "cafe_lifestyle": ("cafe.",),
        "commercial_intensity": (
            "restaurant.",
            "cafe.",
            "supermarket.",
            "shopping_mall.",
        ),
        "nightlife_intensity": ("nightlife.",),
    }.get(signal_ref)
    return expected is not None and term.startswith(expected)


def _signal_value_positive(
    signal_ref: str, value: float | int, unit: str
) -> bool | None:
    if unit == "places":
        return value > 0
    if unit != "m":
        return None
    thresholds = {
        "transit_access": 600,
        "green_access": 600,
        "cafe_lifestyle": 650,
        "daily_convenience": 600,
        "commercial_intensity": 1200,
        "nightlife_intensity": 450,
    }
    if signal_ref == "road_noise":
        return value >= 120
    threshold = thresholds.get(signal_ref)
    return value <= threshold if threshold is not None else None


def _composite_signal_positive(signal_ref: str, value: object) -> bool | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if signal_ref == "residential_calm":
        return value >= 0.5
    if signal_ref == "noise_risk":
        return value >= 0.5
    return None


def _composite_fact(signal_ref: str, value: object) -> tuple[str, str] | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if signal_ref == "residential_calm":
        if value >= 0.5:
            return "entorno más residencial", "entorno más residencial"
        return "mayor actividad", "mayor actividad urbana"
    if signal_ref == "noise_risk":
        if value >= 0.5:
            return "mayor actividad", "mayor exposición a actividad urbana"
        return "menor exposición", "menor exposición a actividad urbana"
    return None


def _phrase(
    signal_ref: str, value: float | int, unit: str, term: str = ""
) -> str | None:
    if signal_ref == "road_noise" and unit == "m":
        if value >= 300:
            return "alejada de los principales corredores"
        if value >= 120:
            return "sin estar directamente sobre una avenida grande"
        return "con una avenida principal relativamente cerca"
    if signal_ref == "transit_access" and unit == "m":
        transport = (
            "subte" if "subway" in term or "subte" in term
            else "tren" if "train" in term or "rail" in term
            else "transporte"
        )
        return (
            f"{transport} relativamente cerca"
            if value <= 600
            else f"con {transport} a una distancia mayor"
        )
    if signal_ref == "green_access" and unit == "m":
        return (
            "espacio verde relativamente cerca"
            if value <= 600
            else "espacio verde a una distancia mayor"
        )
    if signal_ref == "cafe_lifestyle" and unit == "m":
        return (
            "cafés relativamente cerca"
            if value <= 650
            else "cafés a una distancia mayor"
        )
    if signal_ref == "daily_convenience" and unit == "m":
        return (
            "servicios cotidianos relativamente cerca"
            if value <= 600
            else "servicios cotidianos a una distancia mayor"
        )
    if signal_ref == "commercial_intensity" and unit == "m":
        return (
            "actividad comercial relativamente cerca"
            if value <= 1200
            else "actividad comercial a una distancia mayor"
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
    observations: Mapping[str, ListingObservation],
) -> Mapping[str, object]:
    packet: dict[str, object] = {
        "criterion_key": reason.criterion_key,
        "label": _label(reason.criterion_key, active_criteria),
        "state": reason.state,
        "placement": "match" if reason.state == "match" else "tradeoff",
        "confidence": reason.confidence,
        "evidence_refs": _evidence_refs(reason.evidence_refs),
    }
    fact = _evaluation_fact(reason, active_criteria, observations)
    if fact is not None:
        packet["fact"] = fact
    return packet


def _evaluation_fact(
    reason: ExplanationReason,
    active_criteria: Mapping[str, object],
    observations: Mapping[str, ListingObservation],
) -> str | None:
    priority = active_criteria.get(reason.criterion_key)
    polarity = priority.get("polarity") if isinstance(priority, Mapping) else None
    if polarity != "negative" or reason.state != "match":
        return None
    if reason.criterion_key == "luminosidad":
        observation = observations.get(reason.criterion_key)
        value = observation.value if observation is not None else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value <= 0.5:
                return "poca luz natural"
    return None


def _risk_packet(
    risk: ExplanationRisk,
    active_criteria: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "criterion_key": risk.criterion_key,
        "label": _label(risk.criterion_key, active_criteria),
        "state": risk.state,
        "placement": "unknown",
        "evidence_refs": (),
    }


def _priority_packet(key: str, value: object) -> Mapping[str, object]:
    details = value if isinstance(value, Mapping) else {}
    label = details.get("label")
    return {
        "key": key,
        "label": (
            label
            if isinstance(label, str)
            else _DEFAULT_LABELS.get(key, "esta prioridad")
        ),
        "polarity": (
            details.get("polarity")
            if isinstance(details.get("polarity"), str)
            else "positive"
        ),
    }


def _evidence_refs(refs: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(
        f"{ref['kind']}:{ref['ref']}"
        for ref in refs
        if isinstance(ref.get("kind"), str) and isinstance(ref.get("ref"), str)
    )


def _label(key: str, active_criteria: Mapping[str, object]) -> str:
    value = active_criteria.get(key)
    if isinstance(value, Mapping):
        label = value.get("label")
        if isinstance(label, str):
            return label
    return _DEFAULT_LABELS.get(key, "esta prioridad")


def narrative_label(key: str) -> str:
    """Return the human-facing label for a supported narrative criterion."""

    return _DEFAULT_LABELS.get(key, "esta prioridad")


def _packet_evidence_refs(packet: Mapping[str, object] | None) -> tuple[str, ...]:
    if packet is None:
        return ()
    refs = packet.get("evidence_refs")
    if not isinstance(refs, (tuple, list)):
        return ()
    return tuple(ref for ref in refs if isinstance(ref, str))


def _price_change(
    change: Mapping[str, object],
    listing_currency: object,
) -> Mapping[str, object] | None:
    currency = change.get("currency", listing_currency)
    if not _is_complete_price_change(change, currency):
        return None
    return {
        "field": "price",
        "before": change["before"],
        "after": change["after"],
        "currency": currency,
    }


def _is_complete_price_change(change: Mapping[str, object], currency: object) -> bool:
    return (
        change.get("field") in {"price", "price_value"}
        and isinstance(change.get("before"), (int, float))
        and not isinstance(change.get("before"), bool)
        and isinstance(change.get("after"), (int, float))
        and not isinstance(change.get("after"), bool)
        and isinstance(currency, str)
        and bool(currency)
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _join_spanish(values: Sequence[str]) -> str:
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} y {values[1]}"
    return f"{', '.join(values[:-1])} y {values[-1]}"


def _price_text(value: object, currency: object) -> str:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    assert isinstance(currency, str)
    return f"{currency} {value:,.0f}".replace(",", ".")
