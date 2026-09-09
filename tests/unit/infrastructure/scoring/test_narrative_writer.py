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


def test_writer_rejects_evidence_not_tied_to_used_criterion(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    """An authorized reference cannot support a different criterion's claim."""
    scripted_gateway.output = {
        "text": "La superficie es un punto para revisar.",
        "used_criteria": ["superficie"],
        "used_evidence_refs": ["urban:transit-1"],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


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


@pytest.mark.parametrize(
    "text",
    [
        "   ",
        (
            "Esta oportunidad aparece por la conectividad y te permite "
            "organizar mejor cada viaje durante la semana sin perder tiempo "
            "en traslados largos cuando necesitás volver a casa después "
            "del trabajo y resolver tus recorridos cotidianos durante toda "
            "la semana."
        ),
    ],
)
def test_writer_rejects_any_voice_lint_failure(
    scripted_gateway: ScriptedGateway,
    context: ExplanationNarrativeContext,
    text: str,
) -> None:
    """Every linter violation, not only a selected subset, triggers fallback."""
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


def test_writer_rejects_empty_evidence_refs(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": [],
    }

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


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
