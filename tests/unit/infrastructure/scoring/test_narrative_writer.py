"""Safety checks for the presentation-only opportunity narrator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest

from umbral.application.agent.contracts import ModelResult
from umbral.application.scoring.contracts import (
    ExplanationNarrativeContext,
    GeographicFact,
)
from umbral.application.scoring.narrative import deterministic_narrative
from umbral.infrastructure.scoring.narrative import ManagedExplanationNarrativeWriter

ROOT = Path(__file__).resolve().parents[4]
SCHEMA = json.loads(
    (
        ROOT / "contracts" / "scoring" / "v1" / "explanation-narrative-schema.json"
    ).read_text(encoding="utf-8")
)


class ScriptedGateway:
    """Controlled model boundary; assertions target the writer result."""

    def __init__(self) -> None:
        self.output: Mapping[str, object] | None = None
        self.status: Literal["success", "error", "timeout"] = "success"
        self.messages: tuple[Mapping[str, object], ...] = ()

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Any = None,
    ) -> ModelResult:
        self.messages = messages
        return ModelResult(
            content=dict(self.output) if self.output is not None else None,
            model_version=model_version,
            status=self.status,
            latency_ms=1,
        )


@pytest.fixture
def scripted_gateway() -> ScriptedGateway:
    return ScriptedGateway()


@pytest.fixture
def context() -> ExplanationNarrativeContext:
    return ExplanationNarrativeContext(
        listing={"price": 207000, "neighborhood": "Palermo"},
        active_priorities=(
            {
                "key": "acceso_transporte",
                "label": "buena conectividad",
                "polarity": "positive",
            },
        ),
        reasons=(
            {
                "label": "buena conectividad",
                "state": "match",
                "confidence": 0.9,
                "evidence_refs": ("urban:transit-1",),
            },
        ),
        tradeoffs=(
            {
                "label": "superficie",
                "state": "mismatch",
                "evidence_refs": ("listing_field:surface_m2",),
            },
        ),
        unknowns=(),
        geography=(),
        price_changes=(),
        allowed_criteria=("acceso_transporte", "superficie"),
        allowed_evidence_refs=("urban:transit-1", "listing_field:surface_m2"),
        criterion_evidence_refs={
            "acceso_transporte": ("urban:transit-1",),
            "superficie": ("listing_field:surface_m2",),
        },
    )


def _writer(gateway: ScriptedGateway) -> ManagedExplanationNarrativeWriter:
    return ManagedExplanationNarrativeWriter(
        gateway=gateway,
        schema=SCHEMA,
        prompt_version="explanation-narrative-v1",
        model_version="test-model",
    )


def test_writer_rejects_criterion_not_in_context(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A claim about an unasked criterion must not escape the narrator."""
    scripted_gateway.output = {
        "text": "También tiene balcón.",
        "used_criteria": ["balcon"],
        "used_evidence_refs": ["untrusted"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "deterministic_fallback"
    assert "balcón" not in narrative.text.casefold()


def test_writer_rejects_technical_or_certain_geographic_copy(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Technical scores and proxy certainty are unsafe despite valid references."""
    scripted_gateway.output = {
        "text": "Tiene transit_access 0.81 y es totalmente silencioso y seguro.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative == deterministic_narrative(
        context,
        prompt_version="explanation-narrative-v1",
    )


def test_writer_rejects_raw_authorized_criterion_key(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Snake-case criterion names are never user-facing language."""
    scripted_gateway.output = {
        "text": "El acceso_transporte suma para esta oportunidad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_rejects_active_criterion_without_a_grounded_fact(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """An active criterion is not a fact about the selected listing."""
    context = replace(context, allowed_criteria=("acceso_transporte", "balcon"))
    scripted_gateway.output = {
        "text": "También tiene balcón.",
        "used_criteria": ["balcon"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_prompt_lists_only_evidence_backed_criteria(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """The model receives the exact criteria it may cite in metadata."""
    context = replace(
        context,
        active_priorities=(
            *context.active_priorities,
            {"key": "balcon", "label": "balcón", "polarity": "positive"},
        ),
        allowed_criteria=(*context.allowed_criteria, "balcon"),
    )
    scripted_gateway.output = {
        "text": (
            "Encaja por la buena conectividad. "
            "La superficie es un punto para revisar."
        ),
        "used_criteria": ["acceso_transporte", "superficie"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:surface_m2"],
    }

    _writer(scripted_gateway).write(context)

    payload = json.loads(str(scripted_gateway.messages[1]["content"]))
    assert payload["authorized_criteria"] == [
        {"key": "acceso_transporte", "evidence_refs": ["urban:transit-1"]},
        {"key": "superficie", "evidence_refs": ["listing_field:surface_m2"]},
    ]
    assert payload["allowed_criteria"] == ["acceso_transporte", "superficie"]


def test_writer_derives_evidence_refs_from_authorized_criteria(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Provenance is owned by the packet, not by model-produced reference IDs."""
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["model-invented-ref"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_evidence_refs == ("urban:transit-1",)


def test_writer_derives_only_allowed_evidence_refs(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Internal observation refs must not leak into the serving provenance."""
    context = replace(
        context,
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "acceso_transporte": (
                "observation:transit-1",
                "urban:transit-1",
            ),
        },
    )
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": [],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_evidence_refs == ("urban:transit-1",)


def test_writer_preserves_model_selected_subset_of_evidence_refs(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A grounded synthesis may use only some evidence for one criterion."""
    context = replace(
        context,
        allowed_evidence_refs=(*context.allowed_evidence_refs, "urban:noise-2"),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "acceso_transporte": ("urban:transit-1", "urban:noise-2"),
        },
    )
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_evidence_refs == ("urban:transit-1",)


def test_writer_drops_criteria_without_model_selected_evidence(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Criteria without a submitted ref must not make grounded copy fail."""
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte", "superficie"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_criteria == ("acceso_transporte",)
    assert narrative.used_evidence_refs == ("urban:transit-1",)


def test_writer_recovers_omitted_authorized_criteria_from_natural_text(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Natural copy may omit metadata for claims already present in the packet."""
    shopping = GeographicFact(
        label="servicios cotidianos cerca",
        value="servicios cotidianos relativamente cerca",
        source_ref="urban:shopping-1",
        confidence=0.8,
        criterion_key="proximidad_compras",
        favorable=True,
        signal_ref="daily_convenience",
    )
    cafes = GeographicFact(
        label="cafés cercanos",
        value="cafés relativamente cerca",
        source_ref="urban:cafes-1",
        confidence=0.8,
        criterion_key="proximidad_cafes",
        favorable=True,
        signal_ref="cafe_lifestyle",
    )
    residential = GeographicFact(
        label="entorno más residencial",
        value="entorno más residencial",
        source_ref="urban:residential-1",
        confidence=0.8,
        criterion_key="calma_residencial",
        favorable=True,
        signal_ref="residential_calm",
    )
    context = replace(
        context,
        reasons=(),
        tradeoffs=(),
        geography=(shopping, cafes, residential),
        allowed_criteria=(
            "proximidad_compras",
            "proximidad_cafes",
            "calma_residencial",
        ),
        allowed_evidence_refs=(
            shopping.source_ref,
            cafes.source_ref,
            residential.source_ref,
        ),
        criterion_evidence_refs={
            "proximidad_compras": (shopping.source_ref,),
            "proximidad_cafes": (cafes.source_ref,),
            "calma_residencial": (residential.source_ref,),
        },
    )
    scripted_gateway.output = {
        "text": (
            "La zona tiene servicios y cafés cerca, y se siente bastante residencial."
        ),
        "used_criteria": ["calma_residencial"],
        "used_evidence_refs": [residential.source_ref],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert set(narrative.used_criteria) == {
        "proximidad_compras",
        "proximidad_cafes",
        "calma_residencial",
    }
    assert set(narrative.used_evidence_refs) == set(
        context.allowed_evidence_refs
    )


def test_writer_deduplicates_repeated_model_criteria(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Repeated structured criteria must not turn a valid narrative into fallback."""
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte", "acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_criteria == ("acceso_transporte",)


def test_writer_prompt_excludes_unsupported_priorities_and_unknowns(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """The model must not be invited to narrate criteria without evidence."""
    context = replace(
        context,
        active_priorities=(
            *context.active_priorities,
            {"key": "calma_residencial", "label": "entorno tranquilo"},
        ),
        unknowns=(
            {
                "criterion_key": "calma_residencial",
                "label": "entorno tranquilo",
                "state": "unknown",
                "placement": "unknown",
                "evidence_refs": (),
            },
        ),
        allowed_criteria=(*context.allowed_criteria, "calma_residencial"),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "calma_residencial": (),
        },
    )
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    _writer(scripted_gateway).write(context)

    payload = json.loads(str(scripted_gateway.messages[1]["content"]))
    assert payload["allowed_criteria"] == ["acceso_transporte", "superficie"]
    assert payload["unknowns"] == []
    assert [item["key"] for item in payload["active_priorities"]] == [
        "acceso_transporte"
    ]


def test_writer_prompt_exposes_only_renderable_grounded_claims(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """The model must not receive geographic facts the validator cannot authorize."""
    context = replace(
        context,
        geography=(
            GeographicFact(
                label="servicios cotidianos cerca",
                value="servicios cotidianos relativamente cerca",
                source_ref="urban:shopping-1",
                confidence=0.8,
                criterion_key="proximidad_compras",
                favorable=True,
                signal_ref="daily_convenience",
            ),
        ),
        allowed_criteria=(*context.allowed_criteria, "proximidad_compras"),
        allowed_evidence_refs=(*context.allowed_evidence_refs, "urban:shopping-1"),
    )
    scripted_gateway.output = {
        "text": "Está bien conectado para moverte por la ciudad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    payload = json.loads(str(scripted_gateway.messages[1]["content"]))
    assert narrative.source == "managed"
    assert payload["grounded_claims"] == [
        {
            "criterion_key": "acceso_transporte",
            "placement": "match",
            "fact": "buena conectividad",
            "evidence_refs": ["urban:transit-1"],
        },
        {
            "criterion_key": "superficie",
            "placement": "tradeoff",
            "fact": "superficie",
            "evidence_refs": ["listing_field:surface_m2"],
        },
    ]
    assert "geography" not in payload
    assert "servicios" not in json.dumps(payload, ensure_ascii=False)


def test_writer_prompt_exposes_concrete_listing_facts_as_grounded_claims(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    context = replace(
        context,
        listing={
            "price": 207000,
            "total_cost": 207000,
            "surface_m2": 54,
            "neighborhood": "Palermo",
        },
        reasons=(
            {
                "criterion_key": "superficie",
                "label": "superficie",
                "fact": "54 m² de superficie",
                "state": "match",
                "placement": "match",
                "evidence_refs": ("listing_field:surface_m2",),
            },
        ),
        tradeoffs=(),
        allowed_criteria=("superficie",),
        allowed_evidence_refs=("listing_field:surface_m2",),
        criterion_evidence_refs={"superficie": ("listing_field:surface_m2",)},
    )
    scripted_gateway.output = {
        "text": "Tiene 54 m² de superficie y una distribución que parece eficiente.",
        "used_criteria": ["superficie"],
        "used_evidence_refs": ["listing_field:surface_m2"],
    }

    narrative = _writer(scripted_gateway).write(context)

    payload = json.loads(str(scripted_gateway.messages[1]["content"]))
    assert narrative.source == "managed"
    assert payload["grounded_claims"] == [
        {
            "criterion_key": "superficie",
            "placement": "match",
            "fact": "54 m² de superficie",
            "evidence_refs": ["listing_field:surface_m2"],
        },
    ]


def test_writer_accepts_compact_metric_wording_for_surface_fact(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    context = replace(
        context,
        reasons=(
            {
                "criterion_key": "superficie",
                "label": "superficie",
                "fact": "54 m² de superficie",
                "state": "match",
                "placement": "match",
                "evidence_refs": ("listing_field:surface_m2",),
            },
        ),
        tradeoffs=(),
        allowed_criteria=("superficie",),
        allowed_evidence_refs=("listing_field:surface_m2",),
        criterion_evidence_refs={"superficie": ("listing_field:surface_m2",)},
    )
    scripted_gateway.output = {
        "text": "Tiene 54 m² y parece aprovechar bien el espacio.",
        "used_criteria": ["superficie"],
        "used_evidence_refs": ["listing_field:surface_m2"],
    }

    assert _writer(scripted_gateway).write(context).source == "managed"


def test_writer_rejects_unknown_criterion_selected_without_evidence(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """An unknown risk cannot be smuggled into a grounded narrative."""
    context = replace(
        context,
        unknowns=(
            {
                "criterion_key": "calma_residencial",
                "label": "entorno tranquilo",
                "state": "unknown",
                "placement": "unknown",
                "evidence_refs": (),
            },
        ),
        allowed_criteria=(*context.allowed_criteria, "calma_residencial"),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "calma_residencial": (),
        },
    )
    scripted_gateway.output = {
        "text": "Está bien conectado, pero no puedo confirmar un entorno tranquilo.",
        "used_criteria": ["acceso_transporte", "calma_residencial"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_accepts_noise_as_a_natural_exposure_paraphrase(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Natural noise wording remains grounded in the exposure descriptor."""
    fact = GeographicFact(
        label="menor exposición",
        value="menor exposición",
        source_ref="urban:noise-1",
        confidence=0.8,
        criterion_key="ruido_ambiental",
        favorable=False,
        signal_ref="noise_risk",
    )
    context = replace(
        context,
        allowed_criteria=(*context.allowed_criteria, "ruido_ambiental"),
        allowed_evidence_refs=(*context.allowed_evidence_refs, fact.source_ref),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "ruido_ambiental": (fact.source_ref,),
        },
        geography=(fact,),
    )
    scripted_gateway.output = {
        "text": "La zona parece tener menos ruido, así que conviene revisarla.",
        "used_criteria": ["ruido_ambiental"],
        "used_evidence_refs": [fact.source_ref],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"


def test_writer_accepts_noise_as_a_paraphrase_of_urban_activity(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Urban-activity evidence may be expressed as cautious noise wording."""
    fact = GeographicFact(
        label="mayor exposición",
        value="mayor exposición a actividad urbana",
        source_ref="urban:noise-2",
        confidence=0.8,
        criterion_key="ruido_ambiental",
        favorable=False,
        signal_ref="noise_risk",
    )
    context = replace(
        context,
        allowed_criteria=(*context.allowed_criteria, "ruido_ambiental"),
        allowed_evidence_refs=(*context.allowed_evidence_refs, fact.source_ref),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "ruido_ambiental": (fact.source_ref,),
        },
        geography=(fact,),
    )
    scripted_gateway.output = {
        "text": "La zona podría tener algo más de ruido, así que conviene revisarla.",
        "used_criteria": ["ruido_ambiental"],
        "used_evidence_refs": [fact.source_ref],
    }

    assert _writer(scripted_gateway).write(context).source == "managed"


def test_writer_accepts_natural_vocabulary_for_residential_and_noise_claims(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Criterion provenance must allow natural wording used by the product voice."""
    residential = GeographicFact(
        label="entorno más residencial",
        value="entorno más residencial",
        source_ref="urban:residential-1",
        confidence=0.8,
        criterion_key="calma_residencial",
        favorable=True,
        signal_ref="residential_calm",
    )
    noise = GeographicFact(
        label="mayor actividad",
        value="mayor exposición a actividad urbana",
        source_ref="urban:noise-1",
        confidence=0.8,
        criterion_key="ruido_ambiental",
        favorable=False,
        signal_ref="noise_risk",
    )
    context = replace(
        context,
        reasons=(),
        tradeoffs=(),
        geography=(residential, noise),
        allowed_criteria=("calma_residencial", "ruido_ambiental"),
        allowed_evidence_refs=(residential.source_ref, noise.source_ref),
        criterion_evidence_refs={
            "calma_residencial": (residential.source_ref,),
            "ruido_ambiental": (noise.source_ref,),
        },
    )
    scripted_gateway.output = {
        "text": (
            "Esta opción suma por estar en una zona bastante residencial, "
            "aunque el ambiente tiene algo más de actividad y conviene revisarlo."
        ),
        "used_criteria": ["calma_residencial", "ruido_ambiental"],
        "used_evidence_refs": [residential.source_ref, noise.source_ref],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"


def test_writer_accepts_location_framing_for_geographic_evidence(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A geographic claim may naturally be introduced through its location."""
    fact = GeographicFact(
        label="servicios cotidianos cerca",
        value="servicios cotidianos cerca",
        source_ref="urban:services-1",
        confidence=0.8,
        criterion_key="proximidad_compras",
        favorable=True,
        signal_ref="daily_convenience",
    )
    context = replace(
        context,
        allowed_criteria=(*context.allowed_criteria, "proximidad_compras"),
        allowed_evidence_refs=(*context.allowed_evidence_refs, fact.source_ref),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "proximidad_compras": (fact.source_ref,),
        },
        geography=(fact,),
    )
    scripted_gateway.output = {
        "text": "La ubicación tiene servicios cotidianos cerca.",
        "used_criteria": ["proximidad_compras"],
        "used_evidence_refs": [fact.source_ref],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"


def test_writer_rejects_location_framing_without_geographic_evidence(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Location wording remains unauthorized for non-geographic claims."""
    scripted_gateway.output = {
        "text": "La superficie es un punto para revisar y la ubicación es conveniente.",
        "used_criteria": ["superficie"],
        "used_evidence_refs": ["listing_field:surface_m2"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "deterministic_fallback"


def test_writer_logs_rejected_criteria(
    scripted_gateway: ScriptedGateway,
    context: ExplanationNarrativeContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rejected criterion is visible in diagnostics without logging model text."""
    context = replace(context, allowed_criteria=(*context.allowed_criteria, "balcon"))
    scripted_gateway.output = {
        "text": "También tiene balcón.",
        "used_criteria": ["balcon"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    with caplog.at_level("WARNING"):
        narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "deterministic_fallback"
    assert any(
        "unauthorized_criteria=balcon" in record.message
        for record in caplog.records
    )


def test_writer_derives_evidence_when_model_ref_is_not_tied_to_criterion(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """An authorized criterion owns its evidence regardless of model IDs."""
    scripted_gateway.output = {
        "text": "La superficie es un punto para revisar.",
        "used_criteria": ["superficie"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_evidence_refs == ("listing_field:surface_m2",)


def test_writer_rejects_raw_key_when_the_context_label_collides(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A human-label collision cannot allow a snake-case internal key."""
    context = replace(
        context,
        active_priorities=(
            {
                "key": "acceso_transporte",
                "label": "acceso_transporte",
                "polarity": "positive",
            },
        ),
    )
    scripted_gateway.output = {
        "text": "El acceso_transporte suma para esta oportunidad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


@pytest.mark.parametrize("text", ["   ", "Encaja por la buena conectividad!!!"])
def test_writer_rejects_hard_voice_lint_failure(
    scripted_gateway: ScriptedGateway,
    context: ExplanationNarrativeContext,
    text: str,
) -> None:
    """Hard voice violations still trigger the deterministic fallback."""
    scripted_gateway.output = {
        "text": text,
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_rejects_unqualified_noise_absence(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A geographic proxy cannot become a certainty about ambient noise."""
    scripted_gateway.output = {
        "text": "No hay ruido cerca.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_uses_managed_text_only_with_authorized_grounding(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A complete, authorized response is the only managed success path."""
    scripted_gateway.output = {
        "text": (
            "Encaja por la buena conectividad. "
            "La superficie es un punto para revisar."
        ),
        "used_criteria": ["acceso_transporte", "superficie"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:surface_m2"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.text.startswith("Encaja")
    assert narrative.used_criteria == ("acceso_transporte", "superficie")
    assert narrative.used_evidence_refs == (
        "urban:transit-1",
        "listing_field:surface_m2",
    )
    assert narrative.model_version == "test-model"


def test_writer_accepts_natural_managed_copy_with_authorized_grounding(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Natural prose must not be rejected only because it differs from a template."""
    scripted_gateway.output = {
        "text": (
            "Esta oportunidad encaja especialmente bien por la buena conectividad. "
            "La superficie es un punto para revisar."
        ),
        "used_criteria": ["acceso_transporte", "superficie"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:surface_m2"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.text == scripted_gateway.output["text"]


def test_writer_accepts_paraphrased_descriptor_with_authorized_grounding(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """Natural phrasing may paraphrase the packet descriptor.

    The criterion and evidence references still provide provenance.
    """
    scripted_gateway.output = {
        "text": (
            "Está bien conectado para moverte por la ciudad. "
            "La superficie es un punto para revisar."
        ),
        "used_criteria": ["acceso_transporte", "superficie"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:surface_m2"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.text == scripted_gateway.output["text"]


def test_writer_accepts_paraphrased_geography_with_tradeoff_placement(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A geographic fact may be expressed as a contained, user-facing paraphrase."""
    fact = GeographicFact(
        label="actividad nocturna",
        value="mayor actividad nocturna",
        source_ref="urban:nightlife-1",
        confidence=0.8,
        criterion_key="vida_nocturna",
        favorable=False,
        signal_ref="nightlife_intensity",
    )
    context = replace(
        context,
        allowed_criteria=(*context.allowed_criteria, "vida_nocturna"),
        allowed_evidence_refs=(*context.allowed_evidence_refs, fact.source_ref),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            "vida_nocturna": (fact.source_ref,),
        },
        geography=(fact,),
    )
    scripted_gateway.output = {
        "text": (
            "La zona tiene bastante movimiento de noche, así que conviene "
            "revisarla antes de decidir."
        ),
        "used_criteria": ["vida_nocturna"],
        "used_evidence_refs": [fact.source_ref],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.text == scripted_gateway.output["text"]


def test_writer_accepts_grounded_uncertainty_wording(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """User-facing uncertainty is valid and must not trigger the fallback."""
    scripted_gateway.output = {
        "text": (
            "Encaja por la buena conectividad. La superficie es un punto para "
            "revisar; tengo poca evidencia para describirla mejor."
        ),
        "used_criteria": ["acceso_transporte", "superficie"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:surface_m2"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.text == scripted_gateway.output["text"]


def test_writer_rejects_invented_price_change_with_unrelated_valid_reference(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad. Bajó de USD 900.000 a USD 800.000.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }
    narrative = _writer(scripted_gateway).write(context)

    assert narrative == deterministic_narrative(
        context,
        prompt_version="explanation-narrative-v1",
    )


def test_writer_rejects_invented_amenity_with_valid_transport_reference(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad y tiene balcón.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative == deterministic_narrative(
        context,
        prompt_version="explanation-narrative-v1",
    )


def test_writer_rejects_invented_terrace_with_valid_transport_reference(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad y tiene terraza.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_accepts_a_long_but_grounded_narrative_sentence(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """The general reply linter's sentence-length heuristic is not a narrative gate."""
    scripted_gateway.output = {
        "text": (
            "Encaja por la buena conectividad porque te permite resolver tus "
            "recorridos cotidianos con transporte cerca y mantener una conexión "
            "práctica con el resto de la ciudad durante la semana."
        ),
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"


def test_writer_logs_validation_rejection_detail(
    scripted_gateway: ScriptedGateway,
    context: ExplanationNarrativeContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad y tiene terraza.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    with caplog.at_level("WARNING", logger="umbral.infrastructure.scoring.narrative"):
        _writer(scripted_gateway).write(context)

    assert "detail=untracked_property_term" in caplog.text
    assert "criteria=acceso_transporte" in caplog.text
    assert "untracked_terms=terraza" in caplog.text


def test_writer_derives_evidence_when_model_refs_are_empty(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": [],
    }

    narrative = _writer(scripted_gateway).write(context)

    assert narrative.source == "managed"
    assert narrative.used_evidence_refs == ("urban:transit-1",)


@pytest.mark.parametrize(
    ("fact", "text"),
    [
        (
            GeographicFact(
                label="actividad nocturna",
                value="algo de actividad nocturna cerca",
                source_ref="urban:nightlife-1",
                confidence=0.8,
                criterion_key="vida_nocturna",
                favorable=False,
                signal_ref="nightlife_intensity",
            ),
            "Encaja por algo de actividad nocturna cerca.",
        ),
        (
            GeographicFact(
                label="buena conectividad",
                value="subte relativamente cerca",
                source_ref="urban:transit-1",
                confidence=0.8,
                criterion_key="acceso_transporte",
                favorable=True,
                signal_ref="transit_access",
            ),
            "La subte relativamente cerca es un punto para revisar.",
        ),
    ],
)
def test_writer_rejects_geography_with_wrong_placement(
    scripted_gateway: ScriptedGateway,
    context: ExplanationNarrativeContext,
    fact: GeographicFact,
    text: str,
) -> None:
    assert fact.criterion_key is not None
    criterion_key = fact.criterion_key
    scripted_gateway.output = {
        "text": text,
        "used_criteria": [criterion_key],
        "used_evidence_refs": [fact.source_ref],
    }
    context = replace(
        context,
        allowed_criteria=tuple(
            dict.fromkeys((*context.allowed_criteria, criterion_key))
        ),
        allowed_evidence_refs=tuple(
            dict.fromkeys((*context.allowed_evidence_refs, fact.source_ref))
        ),
        criterion_evidence_refs={
            **context.criterion_evidence_refs,
            criterion_key: (fact.source_ref,),
        },
        geography=(fact,),
    )

    narrative = _writer(scripted_gateway).write(context)

    assert narrative == deterministic_narrative(
        context,
        prompt_version="explanation-narrative-v1",
    )


def test_writer_rejects_untracked_claim_after_grounded_claim(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad y tiene vista al río.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_rejects_authorized_unlisted_packet_descriptor(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """A valid catalog descriptor still needs this response's packet provenance."""
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad y la superficie.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


@pytest.mark.parametrize(
    ("text", "used_criteria", "used_evidence_refs"),
    [
        (
            "No encaja por la buena conectividad.",
            ["acceso_transporte"],
            ["urban:transit-1"],
        ),
        (
            "Encaja por la buena conectividad. No tiene buena conectividad.",
            ["acceso_transporte"],
            ["urban:transit-1"],
        ),
        (
            "Encaja por la buena conectividad y la superficie. "
            "La superficie es un punto para revisar.",
            ["acceso_transporte", "superficie"],
            ["urban:transit-1", "listing_field:surface_m2"],
        ),
    ],
)
def test_writer_rejects_semantic_contradictions(
    scripted_gateway: ScriptedGateway,
    context: ExplanationNarrativeContext,
    text: str,
    used_criteria: list[str],
    used_evidence_refs: list[str],
) -> None:
    scripted_gateway.output = {
        "text": text,
        "used_criteria": used_criteria,
        "used_evidence_refs": used_evidence_refs,
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_rejects_inverted_price_transition(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    context = replace(
        context,
        price_changes=({"before": 900, "after": 800, "currency": "USD"},),
        allowed_evidence_refs=(*context.allowed_evidence_refs, "listing_field:price"),
    )
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad. Subió de USD 800 a USD 900.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:price"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_rejects_declared_reference_without_rendered_claim(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    context = replace(
        context,
        price_changes=({"before": 900, "after": 800, "currency": "USD"},),
        allowed_evidence_refs=(*context.allowed_evidence_refs, "listing_field:price"),
    )
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1", "listing_field:price"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_fallback_explains_reason_and_tradeoff_without_jargon(
    context: ExplanationNarrativeContext,
) -> None:
    """The no-provider path still tells the user why the listing appeared."""
    result = deterministic_narrative(context)

    assert "Encaja" in result.text
    assert "preferencia" not in result.text.casefold()
    assert "filtro" not in result.text.casefold()
    assert "superficie" in result.text.casefold()
