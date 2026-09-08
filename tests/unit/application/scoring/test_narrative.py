"""Grounded, presentation-only inputs for opportunity narratives."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.criteria.contracts import ListingObservation
from umbral.application.scoring.contracts import (
    Explanation,
    ExplanationNarrativeContext,
    ExplanationReason,
    ExplanationRisk,
    GeographicFact,
)
from umbral.application.scoring.narrative import (
    build_narrative_context,
    deterministic_narrative,
    geographic_facts,
    select_material_evaluations,
)


def _explanation() -> Explanation:
    reasons = tuple(
        ExplanationReason(
            criterion_key=key,
            state="match",
            score=1.0,
            confidence=0.9,
            contribution=contribution,
            evidence_level="strong",
            reason_code="concept_observed",
            evidence_refs=({"kind": "observation", "ref": key},),
            text=key,
        )
        for key, contribution in (
            ("acceso_transporte", 0.40),
            ("proximidad_cafes", 0.30),
            ("balcon", 0.20),
            ("luminosidad", 0.10),
            ("estado_general", 0.05),
        )
    )
    return Explanation(
        search_profile_id=uuid4(),
        run_id=uuid4(),
        listing_id=uuid4(),
        score_version="v1",
        score=0.8,
        confidence=0.9,
        reasons=reasons,
        risks=(
            ExplanationRisk("superficie", "mismatch", "too_small", "superficie"),
            ExplanationRisk("orientacion", "unknown", "unknown", "orientación"),
            ExplanationRisk("balcon", "unknown", "unknown", "balcón"),
        ),
        missing_data=("orientacion", "balcon"),
        satisfied_filters=(),
        profile_snapshot={},
        feature_snapshot={},
    )


def _urban_observation(
    concept_key: str,
    *,
    signal_ref: str,
    contributors: list[dict[str, object]],
    value: float = 0.82,
) -> ListingObservation:
    now = datetime.now(timezone.utc)
    return ListingObservation(
        observation_id=uuid4(),
        listing_id=uuid4(),
        concept_key=concept_key,
        matcher_type="signal_score",
        value=value,
        score=value,
        confidence=0.8,
        evidence={"signal_ref": signal_ref, "contributors": contributors},
        source="urban",
        extraction_version_id=None,
        state="active",
        failure_code=None,
        recomputation_run_id=None,
        created_at=now,
        correlation_id=uuid4(),
    )


def test_select_material_evaluations_limits_active_matches_and_caveats() -> None:
    selected = select_material_evaluations(
        _explanation(),
        {
            "acceso_transporte": object(),
            "proximidad_cafes": object(),
            "balcon": object(),
            "luminosidad": object(),
            "superficie": object(),
            "orientacion": object(),
        },
    )

    assert [item.criterion_key for item in selected] == [
        "acceso_transporte",
        "proximidad_cafes",
        "balcon",
        "luminosidad",
        "superficie",
        "orientacion",
    ]


def test_geographic_facts_translate_observed_distances_without_signal_scores() -> None:
    facts = geographic_facts(
        {
            "ruido_transito": _urban_observation(
                "ruido_transito",
                signal_ref="road_noise",
                contributors=[
                    {
                        "term": "major_road.nearest_m",
                        "score": 0.4,
                        "observed_value": 220.0,
                        "unit": "m",
                    },
                ],
            ),
            "acceso_transporte": _urban_observation(
                "acceso_transporte",
                signal_ref="transit_access",
                contributors=[
                    {
                        "term": "subway_station.nearest_m",
                        "score": 0.8,
                        "observed_value": 340.0,
                        "unit": "m",
                    },
                ],
            ),
        }
    )

    assert [(fact.label, fact.value) for fact in facts] == [
        ("menor exposición", "sin estar directamente sobre una avenida grande"),
        ("buena conectividad", "subte relativamente cerca"),
    ]
    assert all("road_noise" not in fact.value for fact in facts)
    assert all("0.4" not in fact.value for fact in facts)


def test_geographic_facts_use_proxy_safe_language_for_composite_signals() -> None:
    facts = geographic_facts(
        {
            "calma_residencial": _urban_observation(
                "calma_residencial",
                signal_ref="residential_calm",
                contributors=[],
            ),
        }
    )

    assert [(fact.label, fact.value) for fact in facts] == [
        ("entorno más residencial", "entorno más residencial"),
    ]


def test_high_noise_risk_uses_directionally_correct_proxy_safe_language() -> None:
    facts = geographic_facts(
        {
            "ruido_ambiental": _urban_observation(
                "ruido_ambiental",
                signal_ref="noise_risk",
                contributors=[],
                value=0.82,
            ),
        }
    )

    assert [(fact.label, fact.value) for fact in facts] == [
        ("mayor actividad", "mayor exposición a actividad urbana"),
    ]


def test_low_noise_risk_uses_bounded_favorable_proxy_language() -> None:
    facts = geographic_facts(
        {
            "ruido_ambiental": _urban_observation(
                "ruido_ambiental",
                signal_ref="noise_risk",
                contributors=[],
                value=0.18,
            ),
        }
    )

    assert [(fact.label, fact.value) for fact in facts] == [
        ("menor exposición", "menor exposición a actividad urbana"),
    ]
    assert all("mayor exposición" not in fact.value for fact in facts)
    assert all("0.18" not in fact.value for fact in facts)


def test_narrative_context_keeps_safe_listing_fields_and_material_geography() -> None:
    explanation = _explanation()
    observation = _urban_observation(
        "acceso_transporte",
        signal_ref="transit_access",
        contributors=[
            {
                "term": "subway_station.nearest_m",
                "score": 0.8,
                "observed_value": 340.0,
                "unit": "m",
            },
        ],
    )

    context = build_narrative_context(
        explanation=explanation,
        listing={
            "price_value": 207000,
            "surface_m2": 54,
            "rooms": 2,
            "expenses_value": 185000,
            "neighborhood": "Palermo",
            "description_text": "Departamento con una descripción no autorizada.",
        },
        active_criteria={
            "acceso_transporte": {"label": "transporte cerca", "polarity": "positive"},
            "proximidad_cafes": {"label": "cafés cerca", "polarity": "positive"},
            "balcon": {"label": "balcón", "polarity": "positive"},
            "luminosidad": {"label": "buena luz natural", "polarity": "positive"},
            "superficie": {"label": "superficie", "polarity": "positive"},
            "orientacion": {"label": "orientación", "polarity": "positive"},
        },
        observations={"acceso_transporte": observation},
        price_changes=(
            {"field": "price", "before": 225000, "after": 207000, "currency": "USD"},
        ),
    )

    assert context.listing == {
        "price": 207000,
        "surface_m2": 54,
        "rooms": 2,
        "expenses": 185000,
        "neighborhood": "Palermo",
    }
    assert [fact.value for fact in context.geography] == ["subte relativamente cerca"]
    assert context.price_changes == (
        {"field": "price", "before": 225000, "after": 207000, "currency": "USD"},
    )


def test_narrative_context_excludes_incomplete_price_changes() -> None:
    context = build_narrative_context(
        explanation=_explanation(),
        listing={},
        active_criteria={},
        observations={},
        price_changes=(
            {"field": "price", "before": 225000, "after": 207000},
        ),
    )

    assert context.price_changes == ()


def test_narrative_context_uses_listing_currency_for_price_value_change() -> None:
    context = build_narrative_context(
        explanation=_explanation(),
        listing={"price_currency": "USD"},
        active_criteria={},
        observations={},
        price_changes=(
            {"field": "price_value", "before": 225000, "after": 207000},
        ),
    )

    assert context.price_changes == (
        {"field": "price", "before": 225000, "after": 207000, "currency": "USD"},
    )


def test_narrative_describes_price_increase_without_calling_it_a_drop() -> None:
    context = ExplanationNarrativeContext(
        listing={},
        active_priorities=(),
        reasons=(),
        tradeoffs=(),
        unknowns=(),
        geography=(),
        price_changes=(
            {"field": "price", "before": 100000, "after": 120000, "currency": "USD"},
        ),
        allowed_criteria=(),
        allowed_evidence_refs=(),
    )

    result = deterministic_narrative(context)

    assert "Bajó" not in result.text
    assert "pasó de USD 100.000 a USD 120.000" in result.text
    assert "listing_field:price" in result.used_evidence_refs


def test_material_evaluations_keep_matches_and_tradeoffs_independent() -> None:
    explanation = _explanation()
    selected = select_material_evaluations(
        explanation,
        {
            key: object()
            for key in (
                "acceso_transporte",
                "proximidad_cafes",
                "balcon",
                "luminosidad",
                "superficie",
                "orientacion",
            )
        },
    )
    assert [item.criterion_key for item in selected] == [
        "acceso_transporte",
        "proximidad_cafes",
        "balcon",
        "luminosidad",
        "superficie",
        "orientacion",
    ]


def test_geographic_contributor_requires_matching_term() -> None:
    facts = geographic_facts({
        "acceso_transporte": _urban_observation(
            "acceso_transporte", signal_ref="transit_access", contributors=[
                {
                    "term": "train_station.nearest_m",
                    "observed_value": 200,
                    "unit": "m",
                },
                {
                    "term": "subway_station.nearest_m",
                    "observed_value": 800,
                    "unit": "m",
                },
            ]
        )
    })
    assert facts[0].value == "tren relativamente cerca"


def test_unsupported_geographic_signal_is_omitted() -> None:
    facts = geographic_facts({
        "acceso_escuela": _urban_observation(
            "acceso_escuela",
            signal_ref="school_access",
            contributors=[
                {"term": "school.nearest_m", "observed_value": 250, "unit": "m"},
            ],
        )
    })

    assert facts == ()


def test_avoid_nightlife_is_a_tradeoff_while_desired_nightlife_is_a_match() -> None:
    reason = ExplanationReason(
        criterion_key="vida_nocturna",
        state="match",
        score=1.0,
        confidence=0.9,
        contribution=0.2,
        evidence_level="strong",
        reason_code="signal_observed",
        evidence_refs=({"kind": "observation", "ref": "nightlife"},),
        text="actividad nocturna",
    )
    explanation = replace(_explanation(), reasons=(_explanation().reasons + (reason,)))
    observation = _urban_observation(
        "vida_nocturna",
        signal_ref="nightlife_intensity",
        contributors=[
            {"term": "nightlife.nearest_m", "observed_value": 1, "unit": "places"},
        ],
    )

    desired = build_narrative_context(
        explanation=explanation,
        listing={},
        active_criteria={
            "vida_nocturna": {
                "label": "actividad nocturna",
                "polarity": "positive",
            }
        },
        observations={"vida_nocturna": observation},
    )
    avoided = build_narrative_context(
        explanation=explanation,
        listing={},
        active_criteria={
            "vida_nocturna": {
                "label": "actividad nocturna",
                "polarity": "negative",
            }
        },
        observations={"vida_nocturna": observation},
    )

    assert [fact.value for fact in desired.geography] == [
        "algo de actividad nocturna cerca"
    ]
    assert [item["label"] for item in avoided.tradeoffs] == ["actividad nocturna"]
    avoided_text = deterministic_narrative(avoided).text
    assert not avoided_text.startswith("Encaja por actividad nocturna.")
    assert "Algo de actividad nocturna cerca es un punto para revisar." in avoided_text


def test_avoid_noise_and_desired_noise_have_opposite_placement() -> None:
    reason = ExplanationReason(
        criterion_key="ruido_ambiental",
        state="match",
        score=1.0,
        confidence=0.9,
        contribution=0.2,
        evidence_level="strong",
        reason_code="signal_observed",
        evidence_refs=({"kind": "observation", "ref": "noise"},),
        text="exposición",
    )
    explanation = replace(_explanation(), reasons=(_explanation().reasons + (reason,)))
    observation = _urban_observation(
        "ruido_ambiental",
        signal_ref="noise_risk",
        contributors=[],
        value=0.82,
    )

    desired = build_narrative_context(
        explanation=explanation,
        listing={},
        active_criteria={
            "ruido_ambiental": {
                "label": "mayor actividad",
                "polarity": "positive",
            }
        },
        observations={"ruido_ambiental": observation},
    )
    avoided = build_narrative_context(
        explanation=explanation,
        listing={},
        active_criteria={
            "ruido_ambiental": {
                "label": "menor exposición",
                "polarity": "negative",
            }
        },
        observations={"ruido_ambiental": observation},
    )

    assert [fact.value for fact in desired.geography] == [
        "mayor exposición a actividad urbana"
    ]
    assert [item["label"] for item in avoided.tradeoffs] == ["mayor actividad"]
    assert not deterministic_narrative(avoided).text.startswith(
        "Encaja por mayor actividad."
    )


def test_supported_narrative_criteria_have_human_labels() -> None:
    supported = (
        "presupuesto", "ambientes", "superficie", "ubicacion", "balcon",
        "piso", "tipo_cocina", "luminosidad", "estado_general", "barrio_seguro",
        "moderno", "dormitorios", "banos", "mascotas", "amoblado", "ascensor",
        "cochera", "piscina", "precio_m2", "variacion_precio", "proximidad_cafes",
        "acceso_transporte", "proximidad_parque", "proximidad_compras",
        "vida_nocturna", "zona_comercial", "caminabilidad", "calma_residencial",
        "ruido_transito", "ruido_tren", "ruido_ambiental", "acceso_escuela",
        "acceso_deporte", "acceso_cultura", "acceso_bici", "acceso_salud",
    )
    context = build_narrative_context(
        explanation=_explanation(),
        listing={},
        active_criteria={key: {} for key in supported},
        observations={},
    )

    labels = [item["label"] for item in context.active_priorities]
    assert all(isinstance(label, str) and label != "esta prioridad" for label in labels)
    assert all("_" not in label for label in labels if isinstance(label, str))


def test_fallback_provenance_contains_only_rendered_geography() -> None:
    context = ExplanationNarrativeContext(
        listing={},
        active_priorities=(),
        reasons=(),
        tradeoffs=(),
        unknowns=(),
        geography=tuple(
            GeographicFact(
                label="conectividad",
                value=f"señal {index}",
                source_ref=f"urban:{index}",
                confidence=0.9,
                criterion_key=f"criterio_{index}",
            )
            for index in range(4)
        ),
        price_changes=(),
        allowed_criteria=(),
        allowed_evidence_refs=(),
    )

    result = deterministic_narrative(context)

    assert result.used_criteria == ("criterio_0", "criterio_1", "criterio_2")
    assert result.used_evidence_refs == (
        "urban:0",
        "urban:1",
        "urban:2",
    )
    assert "señal 3" not in result.text
