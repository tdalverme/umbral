"""Safety checks for the presentation-only opportunity narrator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest

from umbral.application.agent.contracts import ModelResult
from umbral.application.scoring.contracts import ExplanationNarrativeContext
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

    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


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


def test_writer_rejects_invented_price_change_with_unrelated_valid_reference(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad. Bajó de USD 900.000 a USD 800.000.",
        "used_criteria": ["acceso_transporte"],
        "used_evidence_refs": ["urban:transit-1"],
    }
    assert _writer(scripted_gateway).write(context).source == "deterministic_fallback"


def test_writer_rejects_invented_amenity_with_valid_transport_reference(
    scripted_gateway: ScriptedGateway, context: ExplanationNarrativeContext
) -> None:
    scripted_gateway.output = {
        "text": "Encaja por la buena conectividad y tiene balcón.",
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


def test_fallback_explains_reason_and_tradeoff_without_jargon(
    context: ExplanationNarrativeContext,
) -> None:
    """The no-provider path still tells the user why the listing appeared."""
    result = deterministic_narrative(context)

    assert "Encaja" in result.text
    assert "preferencia" not in result.text.casefold()
    assert "filtro" not in result.text.casefold()
    assert "superficie" in result.text.casefold()
